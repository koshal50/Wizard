"""Investigation Request data model.

The InvestigationRequest is the complete package sent to the Runtime Engine.
It wraps the Intent with repository information and execution options.

This is the contract between the CLI and the Runtime Engine.
When the Runtime Engine is built, it will accept this exact structure.
"""

from __future__ import annotations

import dataclasses
import os
from dataclasses import dataclass, field

from wizard.cli.models.intent import Intent


@dataclass(frozen=True)
class RepositoryInfo:
    """Information about the target repository.

    Attributes:
        path: Absolute path to the repository on disk.
        type: Repository source type — currently only "local".
    """

    path: str
    type: str = "local"

    def to_dict(self) -> dict:
        """Serialize to a plain dictionary."""
        return {
            "path": self.path,
            "type": self.type,
        }


@dataclass(frozen=True)
class RequestOptions:
    """Execution options that control how the Runtime Engine processes the request.

    Attributes:
        budget: Maximum number of tool executions allowed.
        output_format: Desired output format — "markdown" or "json".
        verbose: Whether to show detailed investigation progress.
        quiet: Whether to suppress all output except the final result.
        planner_url: Base URL of an investigation-planner service. When unset the
            Runtime uses its built-in deterministic planner instead.
        agent_explorer_url: Full URL of an Explorer agent endpoint.
        agent_verifier_url: Full URL of a Verifier agent endpoint.
        sandbox_mode: "local_dev" (run tools on this machine) or "docker".
        browser_enabled: Whether the Runtime may drive a browser.
        browser_backend: "local", "container", or "cdp_url".
        browser_headless: Whether the driven browser runs without a window.
        browser_cdp_url: CDP endpoint, when browser_backend is "cdp_url".
        allowed_domains: Domains the browser may navigate to.
        max_context_tokens: Token ceiling for the context the Runtime packs.

    The three `*_url` fields are the Runtime's agent seams. They are how the CLI
    reaches the planner and the agents at all: the Runtime resolves each seam
    from these exact option keys and silently substitutes its built-in
    deterministic fallback when one is absent, so an unset URL is not an error —
    it is simply a different (offline) investigation. See `from_env` for the
    supported way to set them without editing code.
    """

    budget: int = 100
    output_format: str = "markdown"
    verbose: bool = False
    quiet: bool = False
    planner_url: str | None = None
    agent_explorer_url: str | None = None
    agent_verifier_url: str | None = None
    sandbox_mode: str | None = None
    browser_enabled: bool | None = None
    browser_backend: str | None = None
    browser_headless: bool | None = None
    browser_cdp_url: str | None = None
    allowed_domains: tuple[str, ...] | None = None
    max_context_tokens: int | None = None

    def to_dict(self) -> dict:
        """Serialize to a plain dictionary.

        Unset optional fields are omitted rather than sent as null: the Runtime
        distinguishes "no URL configured" from "a URL that happens to be empty",
        and an explicit null would read as the latter.
        """
        data: dict = {
            "budget": self.budget,
            "output_format": self.output_format,
            "verbose": self.verbose,
            "quiet": self.quiet,
        }
        optional = (
            ("planner_url", self.planner_url),
            ("agent_explorer_url", self.agent_explorer_url),
            ("agent_verifier_url", self.agent_verifier_url),
            ("sandbox_mode", self.sandbox_mode),
            ("browser_enabled", self.browser_enabled),
            ("browser_backend", self.browser_backend),
            ("browser_headless", self.browser_headless),
            ("browser_cdp_url", self.browser_cdp_url),
            ("max_context_tokens", self.max_context_tokens),
        )
        for key, value in optional:
            if value is not None:
                data[key] = value
        if self.allowed_domains:
            data["allowed_domains"] = list(self.allowed_domains)
        return data

    def for_urls(self, urls: "tuple[str, ...] | list[str]") -> "RequestOptions":
        """This option set, extended to actually browse `urls`.

        Three things have to be true together or a named URL is silently
        ignored, and all three are decided here rather than left to the caller:

          1. `browser_enabled` must be on, or the Runtime never starts a
             browser plane and the URL is just a string in `targets`.
          2. `allowed_domains` must contain the URL's host, or the Runtime's
             egress allowlist refuses the navigation fail-closed — the plane
             would start, do nothing, and report no error.
          3. `browser_headless` must be false, or the window the user asked to
             watch is never drawn.

        (1) and (2) are derived, never assumed: the hosts come from the URLs
        themselves, so the allowlist is exactly as wide as what the user typed
        and no wider. An explicitly-set `browser_enabled=True` with no URLs
        stays enabled — that is a deliberate "browse whatever the planner
        finds", not something to override.

        A `WIZARD_ALLOWED_DOMAINS` value is UNIONED rather than replaced: the
        environment names hosts the user trusts generally, and typing one URL
        should not silently revoke them.
        """
        if not urls:
            return self

        from wizard.cli.parser.intent_parser import domains_from_urls

        hosts = list(self.allowed_domains or ())
        for host in domains_from_urls(tuple(urls)):
            if host not in hosts:
                hosts.append(host)

        return dataclasses.replace(
            self,
            browser_enabled=True,
            allowed_domains=tuple(hosts) or None,
            # Only defaulted, never forced: a user who explicitly asked for a
            # headless run keeps it even while naming a URL.
            browser_headless=False if self.browser_headless is None else self.browser_headless,
        )

    @classmethod
    def from_env(cls, environ: "os._Environ[str] | dict[str, str] | None" = None) -> "RequestOptions":
        """Build options from the environment, falling back to the defaults.

        This is how a run is pointed at a live planner and live agents without
        editing code: every field is optional, and an unset variable leaves the
        corresponding default untouched.

            WIZARD_PLANNER_URL     -> planner_url
            WIZARD_EXPLORER_URL    -> agent_explorer_url
            WIZARD_VERIFIER_URL    -> agent_verifier_url
            WIZARD_SANDBOX_MODE    -> sandbox_mode
            WIZARD_BROWSER         -> browser_enabled  ("1"/"true"/"yes" = on)
            WIZARD_BROWSER_BACKEND -> browser_backend  ("local"|"container"|"cdp_url")
            WIZARD_BROWSER_HEADLESS -> browser_headless ("0"/"false"/"no" = show the window)
            WIZARD_BROWSER_CDP_URL -> browser_cdp_url
            WIZARD_ALLOWED_DOMAINS -> allowed_domains  (comma-separated)
            WIZARD_MAX_CONTEXT_TOKENS -> max_context_tokens
            WIZARD_BUDGET          -> budget

        A malformed value raises ValueError rather than being ignored: silently
        dropping a typo'd budget would run the investigation under a limit the
        user did not ask for.
        """
        env = os.environ if environ is None else environ
        defaults = cls()

        def text(name: str) -> str | None:
            raw = env.get(name)
            return raw.strip() if raw and raw.strip() else None

        def integer(name: str) -> int | None:
            raw = text(name)
            if raw is None:
                return None
            try:
                return int(raw)
            except ValueError as exc:
                raise ValueError(f"{name} must be an integer, got {raw!r}") from exc

        def flag(name: str) -> bool | None:
            raw = text(name)
            return None if raw is None else raw.lower() in ("1", "true", "yes", "on")

        domains_raw = text("WIZARD_ALLOWED_DOMAINS")

        return cls(
            budget=integer("WIZARD_BUDGET") or defaults.budget,
            output_format=text("WIZARD_OUTPUT_FORMAT") or defaults.output_format,
            verbose=flag("WIZARD_VERBOSE") or defaults.verbose,
            quiet=flag("WIZARD_QUIET") or defaults.quiet,
            planner_url=text("WIZARD_PLANNER_URL"),
            agent_explorer_url=text("WIZARD_EXPLORER_URL"),
            agent_verifier_url=text("WIZARD_VERIFIER_URL"),
            sandbox_mode=text("WIZARD_SANDBOX_MODE"),
            browser_enabled=flag("WIZARD_BROWSER"),
            browser_backend=text("WIZARD_BROWSER_BACKEND"),
            browser_headless=flag("WIZARD_BROWSER_HEADLESS"),
            browser_cdp_url=text("WIZARD_BROWSER_CDP_URL"),
            allowed_domains=(
                tuple(d.strip() for d in domains_raw.split(",") if d.strip())
                if domains_raw
                else None
            ),
            max_context_tokens=integer("WIZARD_MAX_CONTEXT_TOKENS"),
        )


@dataclass(frozen=True)
class InvestigationRequest:
    """Complete request package sent to the Runtime Engine.

    This is the CLI's final output — the structured message that crosses
    the boundary between the CLI and the Runtime Engine.

    Attributes:
        repository: Information about the target repository.
        intent: The structured user intent.
        options: Execution options.
    """

    repository: RepositoryInfo
    intent: Intent
    options: RequestOptions = field(default_factory=RequestOptions)

    def to_dict(self) -> dict:
        """Serialize the full request to a plain dictionary."""
        return {
            "repository": self.repository.to_dict(),
            "intent": self.intent.to_dict(),
            "options": self.options.to_dict(),
        }
