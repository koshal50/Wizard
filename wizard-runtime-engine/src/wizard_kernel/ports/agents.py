"""Agent ports — Explorer + Verifier. Protocol + Mock + Http. Phase 6."""
from typing import Protocol, runtime_checkable
from wizard_kernel.contracts.agent import ExplorerResponse, VerifierAssessment


@runtime_checkable
class ExplorerPort(Protocol):
    def request(self, context: dict) -> ExplorerResponse: ...


@runtime_checkable
class VerifierPort(Protocol):
    def assess(self, claims: list[dict]) -> VerifierAssessment: ...


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
            tool_request=ToolRequest(tool=tool, parameters=params,
                                     reason="mock: executing planned node action"),
        )


class MockVerifier:
    def __init__(self, n_claims_threshold: int = 1) -> None:
        self._threshold = n_claims_threshold

    def assess(self, claims: list[dict]) -> VerifierAssessment:
        sufficient = len(claims) >= self._threshold
        return VerifierAssessment(
            investigation_id="",
            assessment="overall_sufficient" if sufficient else "needs_more_work",
        )


class HttpExplorer:
    def __init__(self, url: str) -> None:
        self._url = url

    def request(self, context: dict) -> ExplorerResponse:
        import httpx
        # Strip any trust/graph fields before sending (invariant 3)
        safe_context = {k: v for k, v in context.items()
                        if k not in ("trust", "knowledge_graph_raw")}
        r = httpx.post(self._url, json=safe_context, timeout=30)
        r.raise_for_status()
        return ExplorerResponse.model_validate(r.json())


class HttpVerifier:
    def __init__(self, url: str) -> None:
        self._url = url

    def assess(self, claims: list[dict]) -> VerifierAssessment:
        import httpx
        r = httpx.post(self._url, json={"claims": claims}, timeout=30)
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
