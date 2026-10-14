"""Agent ports — Explorer + Verifier. Protocol + Mock + Http. Phase 6."""
import os
from typing import Protocol, runtime_checkable
from wizard_kernel.contracts.agent import ExplorerResponse, VerifierAssessment


def _agent_timeout() -> float:
    """HTTP timeout for a kernel→agent call, in seconds.

    The Explorer/Verifier agents call Cerebras (gpt-oss-120b) behind the shared
    rate gate, so a single decision legitimately spends the gate wait plus model
    inference — well past the old 30s ceiling, which fired as a bare
    "timed out" and killed otherwise-healthy browser progressions right after a
    snapshot. Matches the planner client's generous, env-tunable timeout.
    """
    try:
        return float(os.environ.get("WIZARD_AGENT_TIMEOUT", "180"))
    except ValueError:
        return 180.0


@runtime_checkable
class ExplorerPort(Protocol):
    def request(self, context: dict) -> ExplorerResponse: ...


@runtime_checkable
class VerifierPort(Protocol):
    def assess(self, claims: list[dict], investigation_id: str = "") -> VerifierAssessment: ...


class MockExplorer:
    """Mock Explorer that defers to the node's own planned action.

    In tests without a real n8n webhook, the Explorer should not override
    the Planner's carefully constructed seed nodes with a generic list_tree.
    This mock faithfully returns the node's planned action so tests can
    validate extractor pipelines, hypothesis evaluation, and claim admission.
    """
    def request(self, context: dict) -> ExplorerResponse:
        from wizard_kernel.contracts.agent import ToolRequest
        node_action = context.get("current_node", {}).get("action", {})
        tool = node_action.get("tool", "list_tree")
        params = node_action.get("params", {})
        return ExplorerResponse(
            investigation_id=context.get("investigation_id", ""),
            node_id=context.get('current_node', {}).get('id'),
            tool_request=ToolRequest(tool=tool, parameters=params,
                                     reason="mock: executing planned node action"),
        )


class MockVerifier:
    def __init__(self, n_claims_threshold: int = 1) -> None:
        self._threshold = n_claims_threshold

    def assess(self, claims: list[dict], investigation_id: str = "") -> VerifierAssessment:
        sufficient = len(claims) >= self._threshold
        return VerifierAssessment(
            investigation_id=investigation_id,
            assessment="overall_sufficient" if sufficient else "needs_more_work",
        )


class HttpExplorer:
    def __init__(self, url: str) -> None:
        self._url = url
        self.deadline_at = None

    def request(self, context: dict) -> ExplorerResponse:
        import httpx
        import re
        # Strip any trust/graph fields before sending (invariant 3)
        safe_context = {k: v for k, v in context.items()
                        if k not in ("trust", "knowledge_graph_raw")}
        r = httpx.post(self._url, json=safe_context, timeout=_agent_timeout())
        if r.is_error:
            try:
                detail = r.json().get("detail")
            except (ValueError, AttributeError):
                detail = None
            if isinstance(detail, list):
                detail = "; ".join(
                    str(item.get("msg", "")) for item in detail if isinstance(item, dict)
                )
            if not isinstance(detail, str):
                detail = "agent request failed"
            detail = re.sub(r"(?i)\bBearer\s+\S+", "Bearer [REDACTED]", detail)
            detail = re.sub(
                r"(?i)\b(?:[A-Z0-9_]*API[_-]?KEY|[A-Z0-9_]*_KEY|TOKEN|SECRET|PASSWORD)\b\s*[:=]\s*\S+",
                "[REDACTED]",
                detail,
            )
            error = RuntimeError(f"Explorer HTTP {r.status_code}: {detail[:500]}")
            error.status_code = r.status_code
            error.detail = detail[:500]
            error.request_id = r.headers.get("x-request-id") or r.headers.get("request-id")
            raise error
        data = r.json()
        if not isinstance(data.get('node_id'), str) or not data['node_id'].strip():
            error = RuntimeError('Explorer output failed validation: node_id is required')
            error.detail = str(error)
            raise error
        return ExplorerResponse.model_validate(data)


class HttpVerifier:
    def __init__(self, url: str) -> None:
        self._url = url
        self.deadline_at = None

    def assess(self, claims: list[dict], investigation_id: str = "") -> VerifierAssessment:
        import httpx
        r = httpx.post(self._url,
                       json={"investigation_id": investigation_id, "claims": claims},
                       timeout=_agent_timeout())
        r.raise_for_status()
        data = r.json()
        # Strip trust fields if agent tried to set them (invariant 3)
        data.pop("trust", None)
        return VerifierAssessment.model_validate(data)


# ── Factory ───────────────────────────────────────────────────────────────────

def get_agents(options: dict) -> tuple[ExplorerPort, VerifierPort]:
    """Return (explorer, verifier) based on investigation options.

    If no URL is configured, falls back to mock agents so the kernel
    never hard-crashes on missing external services.
    """
    explorer_url = options.get("agent_explorer_url")
    verifier_url = options.get("agent_verifier_url")
    explorer: ExplorerPort = HttpExplorer(explorer_url) if explorer_url else MockExplorer()
    verifier: VerifierPort = HttpVerifier(verifier_url) if verifier_url else MockVerifier()
    return explorer, verifier


def _remaining_timeout(deadline):
    from datetime import datetime, timezone
    remaining = (datetime.fromisoformat(deadline) - datetime.now(timezone.utc)).total_seconds() if deadline else 30
    if remaining <= 0:
        from wizard_kernel.session.control import DeadlineExceeded
        raise DeadlineExceeded('Investigation deadline reached')
    # This hop includes the shared provider rate-gate wait AND the provider's
    # separately bounded HTTP call. A 30s transport cap could abandon a healthy
    # agent while it was legitimately waiting its turn. Runtime still owns and
    # enforces the absolute investigation deadline.
    return remaining
