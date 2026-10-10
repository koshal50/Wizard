"""Deterministic Tool Request Validator — enforces sandbox policy before execution.

The Runtime must NEVER blindly execute an Explorer Agent's Tool Request.
Before _safe_execute is called, every Tool Request passes through here.

Invariant 3: Agents never execute tools directly.
Invariant 5: No technology-specific knowledge in kernel core.

Checks (in order):
1. Tool exists in the registered toolset.
2. Parameters pass structural validation for the tool.
3. No path traversal (paths must stay inside workspace root).
4. No exact duplicate request in this investigation (prevents agent loop cycles).
5. Budget would not be exceeded (fast-path check).
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from wizard_kernel.contracts.agent import ToolRequest
from wizard_kernel.contracts.actions import fingerprint, normalize

log = logging.getLogger(__name__)

# Tools that require a path parameter — these are path-traversal candidates
_PATH_TOOLS = frozenset({"read_file", "path_exists", "search_files"})

# Tools that execute arbitrary commands — require extra scrutiny
_EXEC_TOOLS = frozenset({"execute_command", "start_process"})

# Browser tools — a browser action is just another tool. Navigation is URL-guarded
# (the egress analog of the path-traversal guard); ALL browser tools are excluded
# from dedup because identical params (e.g. browser_snapshot {}) address a *changed*
# live page — deduping them would wrongly block legitimate re-observation.
_URL_TOOLS = frozenset({"browser_navigate", "http_request"})
BROWSER_TOOLS = frozenset({
    "browser_navigate", "browser_snapshot", "browser_click",
    "browser_type", "browser_back", "browser_extract", "browser_screenshot",
})

# The full set of tools the Runtime accepts from agents
_ALLOWED_TOOLS = frozenset({
    "list_tree", "read_file", "search_files",
    "execute_command", "check_port", "path_exists",
    "start_process", "read_process", "kill_process", "list_processes", "http_request",
}) | BROWSER_TOOLS


@dataclass
class ValidationResult:
    valid: bool
    reason: str = ""
    sanitised_params: dict = field(default_factory=dict)


class ToolRequestValidator:
    """Per-investigation validator. Holds dedup state — never shared across investigations."""

    def __init__(self, workspace_root: str, allowed_domains: list[str] | None = None,
                 browser_enabled: bool = False, read_only: bool = False) -> None:
        self._root = Path(workspace_root).resolve()
        self._browser_enabled = browser_enabled
        self._read_only = read_only
        # Fingerprint set for exact duplicate detection: (tool, stable-json-params)
        self._seen_fingerprints: set[str] = set()
        self._rejected_fingerprints: set[str] = set()
        # Fail-closed egress allowlist for browser_navigate. Empty → block all navigation.
        self._allowed_domains = tuple(allowed_domains or ())
        # Runtime observations, not agent assertions, advance resource state.
        self._reachable_local_endpoints: set[tuple[str, int]] = set()
        self._local_readiness_targets: set[str] = set()
        self._browser_navigated = False
        self._owned_handles: set[str] = set()
        self._observed_selectors: set[str] = set()
        self._page_url = ''

    def register_local_readiness(self, url: str) -> None:
        """Runtime-only admission of a discovered local GET target, not egress."""
        if self._is_loopback_url(url):
            self._local_readiness_targets.add(url)

    def record_execution(self, tool: str, params: dict, payload: dict) -> None:
        """Advance prerequisites only from successful executor results."""
        data = payload.get("data") or {}
        page = data.get('page_observation') or data
        if tool in BROWSER_TOOLS and payload.get('ok') and isinstance(page, dict) and 'controls' in page:
            self._observed_selectors = {c['selector'] for c in page['controls'] if isinstance(c, dict) and c.get('selector')}
            self._page_url = page.get('url') or self._page_url
        if tool == 'start_process' and payload.get('ok') and data.get('handle_id'):
            self._owned_handles.add(data['handle_id'])
        if tool == 'kill_process' and payload.get('ok'):
            self._owned_handles.discard(params.get('handle_id'))
        if tool == "check_port" and payload.get("ok") and data.get("active"):
            host = str(data.get("host", params.get("host", "localhost"))).lower()
            port = data.get("port", params.get("port"))
            if isinstance(port, int):
                endpoint = (self._endpoint_host(host), port)
                if endpoint not in self._reachable_local_endpoints:
                    self._reachable_local_endpoints.add(endpoint)
                    self._rejected_fingerprints.clear()
        elif tool == "browser_navigate" and payload.get("ok"):
            self._browser_navigated = True
            self._rejected_fingerprints.clear()
        elif tool in BROWSER_TOOLS:
            if payload.get("ok"):
                self._rejected_fingerprints.clear()
            else:
                # Do not spend another model decision on an identical browser
                # action after a real executor failure. A successful state
                # change clears this through the branches above.
                self._rejected_fingerprints.add(self._fingerprint(tool, params))

    def validate(self, request: ToolRequest, budget_remaining: int) -> ValidationResult:
        """Run all checks. Returns a ValidationResult with valid=True on pass."""

        if getattr(self, 'control', None):
            self.control.check()
        raw_fingerprint = self._fingerprint(request.tool, request.parameters)
        if raw_fingerprint in self._rejected_fingerprints:
            return ValidationResult(valid=False, reason="Duplicate rejected ToolRequest; choose a different action.")

        def reject(reason: str) -> ValidationResult:
            self._rejected_fingerprints.add(raw_fingerprint)
            return ValidationResult(valid=False, reason=reason)

        if self._read_only and request.tool not in {'read_file', 'list_tree', 'search_files', 'path_exists'}:
            return reject('Explain is read-only; execution, network and browser tools are disabled.')

        # 1. Tool existence check
        if request.tool not in _ALLOWED_TOOLS:
            return reject(f"Unknown tool {request.tool!r}. Agent requested a non-existent tool.")

        if request.tool in BROWSER_TOOLS and not self._browser_enabled:
            return reject("Browser tools are disabled for this investigation.")

        # 2. Budget fast-path: if budget is already 0, reject before any I/O
        if budget_remaining <= 0:
            return reject("Budget exhausted — no more executions allowed.")

        # 3. Path traversal guard for tools that accept paths
        params = dict(request.parameters)
        if request.tool in {'read_process', 'kill_process'} and params.get('handle_id') not in self._owned_handles:
            return reject('Process handle does not belong to this investigation')
        if request.tool in _EXEC_TOOLS:
            path_result = self._validate_path({'path': params.get('cwd', '.')})
            if not path_result.valid:
                return reject(path_result.reason)
            import re
            command = params.get('command', '')
            if not isinstance(command, str) or re.search(r'(?i)(\brm\s+-rf|\bdel\s+/|\bformat\b|\bgit\s+push\b|\bcurl\b.*\|\s*(sh|bash)|\bshutdown\b)', command):
                return reject('Command violates Runtime execution policy')
        if request.tool in _PATH_TOOLS:
            result = self._validate_path(params)
            if not result.valid:
                return reject(result.reason)
            params = result.sanitised_params  # use the resolved, safe params

        # 3b. Egress guard for browser and direct HTTP requests.
        if request.tool in _URL_TOOLS:
            local_readiness = (request.tool == 'http_request' and params.get('method', 'GET') == 'GET'
                               and params.get('url') in self._local_readiness_targets and bool(self._owned_handles))
            url_result = ValidationResult(valid=True, sanitised_params=params) if local_readiness else self._validate_url(params)
            if not url_result.valid:
                return reject(url_result.reason)
            if self._is_loopback_url(params.get("url", "")):
                parsed = urlsplit(params["url"])
                port = parsed.port or (443 if parsed.scheme == "https" else 80)
                endpoint = (self._endpoint_host(parsed.hostname or ""), port)
                if endpoint not in self._reachable_local_endpoints:
                    return reject(
                        "RESOURCE_NOT_READY: local target has no successful Runtime reachability observation; "
                        "discover its endpoint and verify it with check_port before navigation or HTTP."
                    )

        if request.tool in BROWSER_TOOLS - {"browser_navigate"} and not self._browser_navigated:
            return reject("BROWSER_NOT_READY: a successful browser navigation is required before page actions.")

        # 4. Structural validation — required parameters present
        struct_result = self._validate_structure(request.tool, params)
        if not struct_result.valid:
            return reject(struct_result.reason)

        if request.tool in {'browser_click', 'browser_type'} and params.get('selector') not in self._observed_selectors:
            return reject('Selector was not observed in the current browser page schema')

        # 5. Duplicate detection — fingerprint (tool + canonical params).
        #    Browser tools are EXCLUDED: identical params address a changed live
        #    page, so deduping them would wrongly block legitimate re-observation.
        #    Budget still guarantees termination (invariant 7).
        # Read-only live observations may repeat only after resource state changes.
        # Mutations (including fills/clicks/navigation) are never replayed blindly.
        repeatable_observation = request.tool in {
            'read_process', 'check_port', 'list_processes', 'browser_snapshot', 'browser_extract',
        }
        if not repeatable_observation:
            fingerprint = self._fingerprint(request.tool, params)
            if fingerprint in self._seen_fingerprints:
                return reject(
                    (
                        f"Duplicate request: {request.tool!r} with identical parameters has already "
                        "been executed in this investigation. Agent may be in a cycle."
                    )
                )
            self._seen_fingerprints.add(fingerprint)

        return ValidationResult(valid=True, sanitised_params=params)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _validate_path(self, params: dict) -> ValidationResult:
        """Resolve and enforce that path param stays inside the workspace root."""
        raw_path = params.get("path", "")
        if not raw_path:
            # No path specified — tool may still work (e.g. search_files with glob only)
            return ValidationResult(valid=True, sanitised_params=params)
        try:
            resolved = (self._root / raw_path).resolve()
            resolved.relative_to(self._root)  # raises ValueError on traversal
        except ValueError:
            return ValidationResult(
                valid=False,
                reason=(
                    f"Path traversal attempt: {raw_path!r} resolves outside "
                    f"workspace root {self._root}."
                ),
            )
        except Exception as exc:  # noqa: BLE001
            return ValidationResult(valid=False, reason=f"Path validation error: {exc}")

        # Return sanitised params with the resolved relative path string
        safe_params = dict(params)
        safe_params["path"] = str(resolved.relative_to(self._root))
        return ValidationResult(valid=True, sanitised_params=safe_params)

    def _validate_url(self, params: dict) -> ValidationResult:
        """Enforce that a navigation URL is http(s) and its host is allow-listed.

        Fail-closed: an empty allowlist blocks ALL navigation. A host matches only
        if it equals an allowed domain or is a subdomain of it — ``example.com``
        admits ``docs.example.com`` but never ``evil-example.com``."""
        from urllib.parse import urlparse

        raw_url = params.get("url", "")
        if not raw_url:
            return ValidationResult(valid=False, reason="browser_navigate requires a 'url' parameter.")
        parsed = urlparse(raw_url)
        if parsed.scheme not in ("http", "https"):
            return ValidationResult(
                valid=False,
                reason=f"Disallowed URL scheme {parsed.scheme!r}: only http/https is allowed.",
            )
        host = (parsed.hostname or "").lower()
        if not self._allowed_domains:
            return ValidationResult(
                valid=False,
                reason="Request blocked: allowed_domains is empty (fail-closed egress policy).",
            )
        for domain in self._allowed_domains:
            d = domain.lower().lstrip(".")
            if host == d or host.endswith("." + d):
                return ValidationResult(valid=True, sanitised_params=params)
        return ValidationResult(
            valid=False,
            reason=f"Request to {host!r} blocked: not in allowed_domains {list(self._allowed_domains)}.",
        )

    def _validate_structure(self, tool: str, params: dict) -> ValidationResult:
        """Check that required parameters for known tools are present and typed."""
        required: dict[str, type] = {}
        import inspect
        from wizard_kernel.world.tools import ToolExecutor
        handler = getattr(ToolExecutor, f'_tool_{tool}', None)
        if handler is not None:
            allowed = set(inspect.signature(handler).parameters) - {'self'}
            unknown = set(params) - allowed
            if unknown:
                return ValidationResult(False, f'Unsupported parameters: {sorted(unknown)}')
        if tool == 'read_file':
            required = {'path': str}
        if tool == "execute_command":
            required = {"command": str}
        elif tool == "start_process":
            required = {"command": str}
        elif tool == "read_process":
            required = {"handle_id": str}
        elif tool == "kill_process":
            required = {"handle_id": str}
        elif tool == "check_port":
            required = {"port": int}
        elif tool == "browser_navigate":
            required = {"url": str}
        elif tool == "browser_click":
            required = {"selector": str}
        elif tool == "browser_type":
            required = {"selector": str, "text": str}
        elif tool == "http_request":
            required = {"url": str}

        for param_name, param_type in required.items():
            if param_name not in params:
                return ValidationResult(
                    valid=False,
                    reason=f"Tool {tool!r} missing required parameter {param_name!r}.",
                )
            if not isinstance(params[param_name], param_type):
                return ValidationResult(
                    valid=False,
                    reason=(
                        f"Tool {tool!r} parameter {param_name!r} must be "
                        f"{param_type.__name__}, got {type(params[param_name]).__name__}."
                    ),
                )
        if tool == "http_request":
            method = str(params.get("method", "GET")).upper()
            if method not in {"GET", "HEAD", "POST"}:
                return ValidationResult(valid=False, reason="http_request method must be GET, HEAD, or POST.")
            if "body" in params and not isinstance(params["body"], str):
                return ValidationResult(valid=False, reason="http_request body must be a string.")
            params["method"] = method
            if len(params.get("body", "")) > 8192:
                return ValidationResult(valid=False, reason="http_request body exceeds 8192 characters.")
        return ValidationResult(valid=True, sanitised_params=params)

    def _fingerprint(self, tool: str, params: dict) -> str:
        """Stable fingerprint of (tool, params) for dedup. Order-independent on dict keys."""
        return fingerprint(tool, {**params, '_page_url': self._page_url} if tool in BROWSER_TOOLS - {'browser_navigate'} else params)

    @staticmethod
    def _is_loopback_url(url: str) -> bool:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        return host == "localhost" or host.endswith(".localhost") or host in {"127.0.0.1", "::1"}

    @staticmethod
    def _endpoint_host(host: str) -> str:
        lowered = host.lower()
        return "loopback" if lowered == "localhost" or lowered.endswith(".localhost") or lowered in {"127.0.0.1", "::1"} else lowered
