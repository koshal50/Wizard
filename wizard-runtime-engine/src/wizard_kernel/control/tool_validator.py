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
import os
import re
import shlex
from pathlib import PureWindowsPath
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from wizard_kernel.contracts.agent import ToolRequest

log = logging.getLogger(__name__)

# Tools that require a path parameter — these are path-traversal candidates
_PATH_TOOLS = frozenset({"read_file", "path_exists", "search_files"})

# Tools that execute arbitrary commands — require extra scrutiny
_EXEC_TOOLS = frozenset({"execute_command", "start_process"})

# Preserve the legacy Planner's safety policy at the actual execution boundary.
_COMMAND_LEADERS = frozenset("npm pnpm yarn node npx python python3 pip pip3 pytest go cargo docker java mvn gradle ls cat echo true test netstat ss ps lsof".split())
_DANGEROUS_COMMANDS = tuple(re.compile(p, re.I) for p in (
    r"\brm\s+-rf?\b", r"\bmkfs\b", r"\bdd\s+if=", r":\(\)\s*\{\s*:\|:&\s*\}",
    r"\bshutdown\b", r"\breboot\b", r"\bchmod\s+-R\s+777\b", r"\bcurl\b[^\n]*\|\s*(sh|bash)\b",
    r"\bwget\b[^\n]*\|\s*(sh|bash)\b", r">\s*/dev/sd[a-z]", r"\bgit\s+push\b",
))

# Browser tools — a browser action is just another tool. Navigation is URL-guarded
# (the egress analog of the path-traversal guard); ALL browser tools are excluded
# from dedup because identical params (e.g. browser_snapshot {}) address a *changed*
# live page — deduping them would wrongly block legitimate re-observation.
_URL_TOOLS = frozenset({"browser_navigate", "http_request"})
BROWSER_TOOLS = frozenset({
    "browser_navigate", "browser_snapshot", "browser_click",
    "browser_type", "browser_fill_form", "browser_back", "browser_extract",
    "browser_assertion", "browser_screenshot",
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
                 browser_enabled: bool = False, navigation_targets: list[str] | None = None, read_only: bool = False) -> None:
        self._root = Path(workspace_root).resolve()
        self._read_only = read_only
        self._browser_enabled = browser_enabled
        # Fingerprint set for exact duplicate detection: (tool, stable-json-params)
        self._seen_fingerprints: set[str] = set()
        self._recheck_permits: dict[str, frozenset[str]] = {}
        self._authorized_rechecks: set[str] = set()
        self._rejected_fingerprints: set[str] = set()
        # Fail-closed egress allowlist for browser_navigate. Empty → block all navigation.
        self._allowed_domains = tuple(allowed_domains or ())
        # Runtime observations, not agent assertions, advance resource state.
        self._reachable_local_endpoints: set[tuple[str, int]] = set()
        self._endpoint_owners: dict[tuple[str, int], str] = {}
        self._process_handles: set[str] = set()
        self._browser_navigated = False
        self._browser_navigation_attempted = False
        self._enforce_discovered_routes = navigation_targets is not None
        self._discovered_urls = {self._navigation_key(url) for url in (navigation_targets or []) if url.startswith(("http://", "https://"))}

    def record_execution(self, tool: str, params: dict, payload: dict) -> None:
        """Advance prerequisites only from successful executor results."""
        data = payload.get("data") or {}
        if payload.get("ok") and tool in BROWSER_TOOLS:
            page = data.get("page_observation") or data
            for link in page.get("links", []):
                if isinstance(link, dict) and link.get("href", "").startswith(("http://", "https://")):
                    self._discovered_urls.add(self._navigation_key(link["href"]))
            if page.get("url"):
                self._discovered_urls.add(self._navigation_key(page["url"]))
        if tool in _URL_TOOLS and not payload.get("ok") and params.get("url"):
            parsed = urlsplit(params["url"])
            endpoint = (self._endpoint_host(parsed.hostname or ""), parsed.port or (443 if parsed.scheme == "https" else 80))
            self._reachable_local_endpoints.discard(endpoint)
            self._endpoint_owners.pop(endpoint, None)
        if tool == "check_port" and payload.get("ok"):
            host = str(data.get("host", params.get("host", "localhost"))).lower()
            port = data.get("port", params.get("port"))
            if isinstance(port, int):
                endpoint = (self._endpoint_host(host), port)
                if not data.get("active"):
                    self._reachable_local_endpoints.discard(endpoint)
                    self._endpoint_owners.pop(endpoint, None)
                    return
                handle = (payload.get("meta") or {}).get("handle_id")
                if handle:
                    self._endpoint_owners[endpoint] = handle
                if endpoint not in self._reachable_local_endpoints:
                    self._reachable_local_endpoints.add(endpoint)
                    self._rejected_fingerprints.clear()
        elif tool == "start_process" and payload.get("ok"):
            handle = data.get("handle_id") or (payload.get("meta") or {}).get("handle_id")
            if handle:
                self._process_handles.add(handle)
        elif (tool == "read_process" and data.get("is_running") is False) or tool == "kill_process":
            handle = data.get("handle_id") or data.get("killed")
            for endpoint, owner in list(self._endpoint_owners.items()):
                if owner == handle:
                    self._reachable_local_endpoints.discard(endpoint)
                    self._endpoint_owners.pop(endpoint, None)
        elif tool == "browser_navigate":
            self._browser_navigation_attempted = True
            self._rejected_fingerprints.discard(self._fingerprint("browser_screenshot", {}))
            self._browser_navigated = bool(payload.get("ok"))
            if self._browser_navigated:
                self._rejected_fingerprints.clear()
            else:
                self._rejected_fingerprints.add(self._fingerprint(tool, params))
        elif tool in BROWSER_TOOLS:
            if payload.get("ok"):
                self._rejected_fingerprints.clear()
            else:
                # Do not spend another model decision on an identical browser
                # action after a real executor failure. A successful state
                # change clears this through the branches above.
                self._rejected_fingerprints.add(self._fingerprint(tool, params))

    def authorize_recheck(self, request: ToolRequest, proof_ids: set[str]) -> bool:
        """Runtime-only, single-use recheck after observed recovery prerequisites.

        This never bypasses tool, command, path, capability or budget checks.
        Agents cannot supply permits through ToolRequest parameters.
        """
        fingerprint = self._fingerprint(request.tool, request.parameters)
        if request.tool != "execute_command" or not proof_ids or fingerprint in self._authorized_rechecks:
            return False
        self._authorized_rechecks.add(fingerprint)
        self._recheck_permits[fingerprint] = frozenset(proof_ids)
        return True

    def validate(self, request: ToolRequest, budget_remaining: int) -> ValidationResult:
        """Run all checks. Returns a ValidationResult with valid=True on pass."""

        raw_fingerprint = self._fingerprint(request.tool, request.parameters)
        recheck = self._recheck_permits.pop(raw_fingerprint, None)
        if raw_fingerprint in self._rejected_fingerprints and not recheck:
            return ValidationResult(valid=False, reason="Duplicate rejected ToolRequest; choose a different action.")

        def reject(reason: str) -> ValidationResult:
            self._rejected_fingerprints.add(raw_fingerprint)
            return ValidationResult(valid=False, reason=reason)

        if self._read_only and request.tool not in {"read_file", "list_tree", "search_files", "path_exists"}:
            return reject("Explain is read-only; execution, network and browser tools are disabled.")

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
        if request.tool in {"read_process", "kill_process"} and params.get("handle_id") not in self._process_handles:
            return reject("Process handle does not belong to this investigation")
        if request.tool in _EXEC_TOOLS:
            command = params.get("command")
            if not isinstance(command, str) or not command.strip():
                return reject("Command must be a nonempty string")
            if any(pattern.search(command) for pattern in _DANGEROUS_COMMANDS):
                return reject("Command matched the existing destructive/exfiltration restriction")
            try:
                words = shlex.split(command, posix=False)
                leader = next(w for w in words if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", w)).strip("\"'")
            except (ValueError, StopIteration):
                return reject("Command has invalid quoting or no executable")
            base = PureWindowsPath(leader).name.lower().removesuffix(".exe")
            allowed = _COMMAND_LEADERS | set(os.environ.get("WIZARD_ALLOWED_COMMANDS", "").split(","))
            if base not in allowed:
                return reject("Command executable is not authorized; configure WIZARD_ALLOWED_COMMANDS for an additional declared entry point")
            try:
                cwd = (self._root / params.get("cwd", ".")).resolve()
                params["cwd"] = str(cwd.relative_to(self._root))
            except (ValueError, TypeError):
                return reject("Command working directory must stay inside the investigation workspace")
        if request.tool == "check_port":
            port = params.get("port")
            if type(port) is not int or not 1 <= port <= 65535:
                return reject("check_port port must be an integer from 1 to 65535")
            host = params.get("host", "localhost")
            if not isinstance(host, str):
                return reject("check_port host must be a string")
            if self._endpoint_host(host) != "loopback" and not any(host == d or host.endswith("." + d) for d in self._allowed_domains):
                return reject("check_port target is outside allowed_domains")
        if request.tool in _PATH_TOOLS:
            result = self._validate_path(params)
            if not result.valid:
                return reject(result.reason)
            params = result.sanitised_params  # use the resolved, safe params

        # 3b. Egress guard for browser and direct HTTP requests.
        if request.tool in _URL_TOOLS:
            url_result = self._validate_url(params)
            if not url_result.valid:
                return reject(url_result.reason)
            if request.tool == "browser_navigate" and self._enforce_discovered_routes:
                parsed = urlsplit(params.get("url", ""))
                # A reachable endpoint permits initial origin discovery only.
                # Application paths must come from an explicit target or real links.
                if (parsed.path not in {"", "/"} or parsed.query) and self._navigation_key(params["url"]) not in self._discovered_urls:
                    return reject("UNDISCOVERED_BROWSER_TARGET: navigate to the discovered origin, take a snapshot, and use an observed link/ref; do not invent application routes")
            if (request.tool != "http_request" or params.get("require_ready", False)) and self._is_loopback_url(params.get("url", "")):
                parsed = urlsplit(params["url"])
                port = parsed.port or (443 if parsed.scheme == "https" else 80)
                endpoint = (self._endpoint_host(parsed.hostname or ""), port)
                if endpoint not in self._reachable_local_endpoints:
                    return reject(
                        "RESOURCE_NOT_READY: local target has no successful Runtime reachability observation; "
                        "discover its endpoint and verify it with check_port before navigation or HTTP."
                    )

        diagnostic_capture = request.tool == "browser_screenshot" and self._browser_navigation_attempted
        if request.tool in BROWSER_TOOLS - {"browser_navigate"} and not self._browser_navigated and not diagnostic_capture:
            return reject("BROWSER_NOT_READY: a successful browser navigation is required before page actions.")

        # 4. Structural validation — required parameters present
        struct_result = self._validate_structure(request.tool, params)
        if not struct_result.valid:
            return reject(struct_result.reason)

        # 5. Duplicate detection — fingerprint (tool + canonical params).
        #    Browser tools are EXCLUDED: identical params address a changed live
        #    page, so deduping them would wrongly block legitimate re-observation.
        #    Budget still guarantees termination (invariant 7).
        repeatable_observation = request.tool in BROWSER_TOOLS | {
            "read_process", "check_port", "list_processes",
        } or (
            request.tool == "http_request"
            and str(params.get("method", "GET")).upper() in {"GET", "HEAD"}
        )
        if not repeatable_observation:
            fingerprint = self._fingerprint(request.tool, params)
            if fingerprint in self._seen_fingerprints and not recheck:
                return reject(
                    (
                        f"Duplicate request: {request.tool!r} with identical parameters has already "
                        "been executed in this investigation. Agent may be in a cycle."
                    )
                )
            self._seen_fingerprints.add(fingerprint)

        return ValidationResult(valid=True, sanitised_params=params)

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _navigation_key(url):
        parsed = urlsplit(url)
        return (parsed.scheme.lower(), ToolRequestValidator._endpoint_host(parsed.hostname or ""),
                parsed.port or (443 if parsed.scheme == "https" else 80), parsed.path or "/", parsed.query)

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
        if parsed.username or parsed.password:
            return ValidationResult(valid=False, reason="Credential-bearing URLs are not allowed")
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
        elif tool == "browser_assertion":
            required = {"field": str, "operator": str, "expected": str}
            if params.get("field") not in {"url", "title", "snapshot", "text"} or params.get("operator") not in {"equals", "contains", "not_contains"}:
                return ValidationResult(valid=False, reason="Unsupported browser assertion")
        elif tool == "browser_type":
            required = {"selector": str, "text": str}
        elif tool == "browser_fill_form":
            required = {"fields": list}
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
        if tool == "browser_fill_form":
            fields = params["fields"]
            if not fields:
                return ValidationResult(valid=False, reason="browser_fill_form fields must not be empty.")
            for index, field in enumerate(fields):
                if (not isinstance(field, dict)
                        or not isinstance(field.get("selector"), str)
                        or not field.get("selector")
                        or not isinstance(field.get("text"), str)):
                    return ValidationResult(
                        valid=False,
                        reason=f"browser_fill_form fields[{index}] requires string selector and text.",
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

    @staticmethod
    def _fingerprint(tool: str, params: dict) -> str:
        """Stable fingerprint of (tool, params) for dedup. Order-independent on dict keys."""
        canonical = json.dumps({"tool": tool, "params": params}, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()

    @staticmethod
    def _is_loopback_url(url: str) -> bool:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        return host == "localhost" or host.endswith(".localhost") or host in {"127.0.0.1", "::1"}

    @staticmethod
    def _endpoint_host(host: str) -> str:
        lowered = host.lower()
        return "loopback" if lowered == "localhost" or lowered.endswith(".localhost") or lowered in {"127.0.0.1", "::1"} else lowered
