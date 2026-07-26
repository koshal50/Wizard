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
    def request(self, context: dict) -> ExplorerResponse:
        from wizard_kernel.contracts.agent import ToolRequest
        return ExplorerResponse(
            investigation_id=context.get("investigation_id", ""),
            tool_request=ToolRequest(tool="list_tree", parameters={"max_depth": 2}),
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
