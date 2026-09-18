"""Command handler: wizard verify <target>

Service function called by the TUI when the user selects "verify"
from the menu. Orchestrates the existing CLI pipeline:

    Step 1 -- Command Parsing:      Validate target against known targets
    Step 2 -- Intent Construction:   Build a typed Intent from parsed components
    Step 3 -- Request Assembly:      Package Intent + repo + options into InvestigationRequest
    Step 4 -- Runtime Communication: Stream events from the Runtime Engine

The verify command tells Wizard to verify whether a specific aspect of
the repository works correctly. This is more rigorous than investigate --
it continues gathering evidence until it can produce a confident verdict
(verified, failed, or uncertain with reasons).

This handler contains ZERO domain logic. It does not know what
"runtime" or "dependencies" means in a verification context. It only
knows how to translate the user's selection into a structured request
and stream the response.
"""

from __future__ import annotations

import os
from typing import Iterator

from wizard.cli.parser.command_parser import validate_target
from wizard.cli.parser.intent_builder import build_intent
from wizard.cli.parser.intent_parser import parse_intent, validate_parsed
from wizard.cli.models.investigation_request import (
    InvestigationRequest,
    RepositoryInfo,
    RequestOptions,
)
from wizard.cli.runtime_client.client import stream_events


def verify(
    target: str,
    repo_path: str | None = None,
    options: RequestOptions | None = None,
    intent_text: str = "",
) -> Iterator[dict]:
    """Run the verify pipeline, yielding engine events.

    Called by the TUI session when the user selects verify + target.
    Validation errors raise CommandValidationError (caller handles display).

    Args:
        target: What to verify (e.g. "runtime", "dependencies"). May be empty
            when the user typed their intent instead of picking a target.
        repo_path: Absolute path to the repository. Defaults to cwd.
        options: Execution options. Defaults to RequestOptions.from_env().
        intent_text: The user's free text, if any. Parsed deterministically
            into extra targets and browser URLs; see intent_parser.

    Yields:
        Engine event dicts from stream_events().
    """
    repo_path = repo_path or os.getcwd()
    options = options or RequestOptions.from_env()

    # Step 1: Command Parsing -- merge the menu's target with the free text,
    # then validate. The parse runs BEFORE validation so a target typed in the
    # text box is validated exactly like one picked from the menu.
    parsed = parse_intent(intent_text, "verify", menu_target=target or None)
    validate_parsed(parsed)
    validate_target("verify", parsed.targets[0])

    # Step 2: Intent Construction -- Build the Intent.
    #
    # Same rule as investigate: a URL the user typed wins, and otherwise a web
    # client the checkout is already serving is browsed without being asked
    # for. See the comment there for why only a listening one qualifies.
    urls = list(parsed.urls)
    if not urls:
        from wizard.cli.parser.frontend import browsable

        found = browsable(repo_path)
        if found is not None:
            urls = [found.url]

    intent = build_intent(
        action="verify",
        targets=list(parsed.targets),
        urls=urls,
        question=intent_text,
    )

    # Step 3: Investigation Request Assembly -- Package everything. Enabling the
    # browser is derived from the URLs the user actually typed.
    request = InvestigationRequest(
        repository=RepositoryInfo(path=repo_path),
        intent=intent,
        options=options.for_urls(intent.urls),
    )

    # Step 4: Runtime Engine Communication -- Stream events
    yield from stream_events(request)
