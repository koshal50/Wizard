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

from wizard_kernel.contracts.agent import ToolRequest

log = logging.getLogger(__name__)

# Tools that require a path parameter — these are path-traversal candidates
_PATH_TOOLS = frozenset({"read_file", "path_exists", "search_files"})

# Tools that execute arbitrary commands — require extra scrutiny
_EXEC_TOOLS = frozenset({"execute_command", "start_process"})

# Browser tools — a browser action is just another tool. Navigation is URL-guarded
# (the egress analog of the path-traversal guard); ALL browser tools are excluded
# from dedup because identical params (e.g. browser_snapshot {}) address a *changed*
# live page — deduping them would wrongly block legitimate re-observation.
_URL_TOOLS = frozenset({"browser_navigate"})
_BROWSER_TOOLS = frozenset({
    "browser_navigate", "browser_snapshot", "browser_click",
    "browser_type", "browser_back", "browser_extract",
})

# The full set of tools the Runtime accepts from agents
_ALLOWED_TOOLS = frozenset({
    "list_tree", "read_file", "search_files",
    "execute_command", "check_port", "path_exists",
    "start_process", "read_process", "kill_process", "list_processes",
}) | _BROWSER_TOOLS


@dataclass
class ValidationResult:
    valid: bool
    reason: str = ""
    sanitised_params: dict = field(default_factory=dict)


class ToolRequestValidator:
    """Per-investigation validator. Holds dedup state — never shared across investigations."""

    def __init__(self, workspace_root: str, allowed_domains: list[str] | None = None) -> None:
        self._root = Path(workspace_root).resolve()
        # Fingerprint set for exact duplicate detection: (tool, stable-json-params)
        self._seen_fingerprints: set[str] = set()
        # Fail-closed egress allowlist for browser_navigate. Empty → block all navigation.
        self._allowed_domains = tuple(allowed_domains or ())

    def validate(self, request: ToolRequest, budget_remaining: int) -> ValidationResult:
        """Run all checks. Returns a ValidationResult with valid=True on pass."""

        # 1. Tool existence check
        if request.tool not in _ALLOWED_TOOLS:
            return ValidationResult(
                valid=False,
                reason=f"Unknown tool {request.tool!r}. Agent requested a non-existent tool.",
            )

        # 2. Budget fast-path: if budget is already 0, reject before any I/O
        if budget_remaining <= 0:
            return ValidationResult(valid=False, reason="Budget exhausted — no more executions allowed.")

        # 3. Path traversal guard for tools that accept paths
        params = dict(request.parameters)
        if request.tool in _PATH_TOOLS:
            result = self._validate_path(params)
            if not result.valid:
                return result
            params = result.sanitised_params  # use the resolved, safe params

        # 3b. URL egress guard for browser navigation (analog of path traversal)
        if request.tool in _URL_TOOLS:
            url_result = self._validate_url(params)
            if not url_result.valid:
                return url_result

        # 4. Structural validation — required parameters present
        struct_result = self._validate_structure(request.tool, params)
        if not struct_result.valid:
            return struct_result

        # 5. Duplicate detection — fingerprint (tool + canonical params).
        #    Browser tools are EXCLUDED: identical params address a changed live
        #    page, so deduping them would wrongly block legitimate re-observation.
        #    Budget still guarantees termination (invariant 7).
        if request.tool not in _BROWSER_TOOLS:
            fingerprint = self._fingerprint(request.tool, params)
            if fingerprint in self._seen_fingerprints:
                return ValidationResult(
                    valid=False,
                    reason=(
                        f"Duplicate request: {request.tool!r} with identical parameters has already "
                        "been executed in this investigation. Agent may be in a cycle."
                    ),
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
                reason=f"Disallowed URL scheme {parsed.scheme!r}: only http/https may be navigated.",
            )
        host = (parsed.hostname or "").lower()
        if not self._allowed_domains:
            return ValidationResult(
                valid=False,
                reason="Navigation blocked: allowed_domains is empty (fail-closed egress policy).",
            )
        for domain in self._allowed_domains:
            d = domain.lower().lstrip(".")
            if host == d or host.endswith("." + d):
                return ValidationResult(valid=True, sanitised_params=params)
        return ValidationResult(
            valid=False,
            reason=f"Navigation to {host!r} blocked: not in allowed_domains {list(self._allowed_domains)}.",
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
        elif tool == "browser_type":
            required = {"selector": str, "text": str}

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
        return ValidationResult(valid=True, sanitised_params=params)

    @staticmethod
    def _fingerprint(tool: str, params: dict) -> str:
        """Stable fingerprint of (tool, params) for dedup. Order-independent on dict keys."""
        canonical = json.dumps({"tool": tool, "params": params}, sort_keys=True, default=str)
        return hashlib.sha256(canonical.encode()).hexdigest()
