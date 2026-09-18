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
    # Headless by default so an unattended run (a test, a CI job, a background
    # investigation) never throws a window onto someone's desktop. A human who
    # wants to watch the agent work sets this false and gets the real Chromium.
    browser_headless: bool = True
    # Fail-closed egress allowlist: empty list blocks ALL navigation (never wide-open).
    allowed_domains: list[str] = Field(default_factory=list)


class InvestigationRequest(BaseModel):
    contracts_version: str = "1.0"
    repository_path: str
    intent: Literal["verify", "investigate", "explain", "report"]
    targets: list[str] = Field(default_factory=list)
    # What the user typed, verbatim, when they typed anything. `intent` is the
    # command family — one of four verbs — and is deliberately not free text;
    # this is the sentence itself, carried unparsed so the Planner can read what
    # was asked rather than only what the command vocabulary recognised in it.
    # Empty for a menu-driven run, which is a run where the family is the whole
    # request.
    question: str = ""
    options: InvestigationOptions = Field(default_factory=InvestigationOptions)
