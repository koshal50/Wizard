from typing import Literal
from pydantic import BaseModel, Field


class InvestigationOptions(BaseModel):
    budget: int = 40
    sandbox_mode: Literal["docker", "local_dev"] = "local_dev"
    planner_url: str | None = None
    agent_explorer_url: str | None = None
    agent_verifier_url: str | None = None
    # ── Agentic browser (opt-in; see agentic-browser-architecture.md §7) ──
    # Off by default → existing investigations are byte-for-byte unaffected.
    browser_enabled: bool = False
    browser_backend: Literal["local", "container", "cdp_url"] = "local"
    browser_cdp_url: str | None = None
    # Fail-closed egress allowlist: empty list blocks ALL navigation (never wide-open).
    allowed_domains: list[str] = Field(default_factory=list)


class InvestigationRequest(BaseModel):
    contracts_version: str = "1.0"
    repository_path: str
    intent: Literal["verify", "investigate", "explain", "report"]
    targets: list[str] = Field(default_factory=list)
    options: InvestigationOptions = Field(default_factory=InvestigationOptions)
