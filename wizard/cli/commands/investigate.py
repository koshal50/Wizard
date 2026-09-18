"""Command handler: wizard investigate <target>

Service function called by the TUI when the user selects "investigate"
from the menu. Orchestrates the existing CLI pipeline:

    Step 1 — Command Parsing:     Validate target against known targets
    Step 2 — Intent Construction: Build a typed Intent from parsed components
    Step 3 — Request Assembly:    Package Intent + repo + options into InvestigationRequest
    Step 4 — Runtime Communication: Stream events from the Runtime Engine

The investigate command tells Wizard to explore a specific aspect of
the repository and explain what it finds. The focus is on understanding —
it does not aim for a pass/fail verdict.

This handler contains ZERO domain logic. It does not know what
"architecture" or "security" means. It only knows how to translate
the user's selection into a structured request and stream the response.
"""

from __future__ import annotations

import os
from typing import Iterator

from wizard.cli.parser.command_parser import validate_target
from wizard.cli.parser.intent_builder import build_intent
from wizard.cli.parser.intent_parser import ParsedIntent, parse_intent, validate_parsed
from wizard.cli.models.investigation_request import (
    InvestigationRequest,
    RepositoryInfo,
    RequestOptions,
)
from wizard.cli.runtime_client.client import stream_events


def investigate(
    target: str,
    repo_path: str | None = None,
    options: RequestOptions | None = None,
    intent_text: str = "",
) -> Iterator[dict]:
    """Run the investigate pipeline, yielding engine events.

    Called by the TUI session when the user selects investigate + target.
    Validation errors raise CommandValidationError (caller handles display).

    Args:
        target: What to investigate (e.g. "architecture", "security"). May be
            empty when the user typed their intent instead of picking a
            target — the parse below then supplies it.
        repo_path: Absolute path to the repository. Defaults to cwd.
        options: Execution options. Defaults to RequestOptions.from_env().
        intent_text: The user's free text, if any. Parsed deterministically
            into extra targets and browser URLs; see intent_parser.

    Yields:
        Engine event dicts from stream_events().
    """
    repo_path = repo_path or os.getcwd()
    # from_env, not a bare RequestOptions(): the Runtime takes its planner and
    # agent endpoints from these options, so the default has to be the
    # environment's, or a caller that omits `options` silently gets an
    # offline-only investigation with no way to tell.
    options = options or RequestOptions.from_env()

    # Step 1: Command Parsing — merge the menu's target with the free text, then
    # validate. The parse runs BEFORE validation so a target typed in the text
    # box is validated exactly like one picked from the menu.
    parsed = parse_intent(intent_text, "investigate", menu_target=target or None)
    validate_parsed(parsed)
    validate_target("investigate", parsed.targets[0])

    # Step 2: Intent Construction — Build the Intent.
    #
    # A URL the user typed wins and is used exactly as typed. When they named
    # none, the checkout is asked whether it is serving a web client, and one
    # that is *already answering* is put into the request on their behalf —
    # because the alternative was a run that silently contained no browser
    # steps and nothing on screen saying a URL was the missing piece. Only a
    # client that answers qualifies (see frontend.browsable): pointing the
    # browser at a port nothing is listening on would fail to navigate and
    # report that failure as the wizard's.
    urls = list(parsed.urls)
    if not urls:
        from wizard.cli.parser.frontend import browsable

        found = browsable(repo_path)
        if found is not None:
            urls = [found.url]

    intent = build_intent(
        action="investigate",
        targets=list(parsed.targets),
        urls=urls,
        question=intent_text,
    )

    # Step 3: Investigation Request Assembly — Package everything. Enabling the
    # browser is derived from the URLs the user actually typed, so nothing is
    # browsed that was not asked for.
    request = InvestigationRequest(
        repository=RepositoryInfo(path=repo_path),
        intent=intent,
        options=options.for_urls(intent.urls),
    )

    # Step 4: Runtime Engine Communication — Stream events
    yield from stream_events(request)
