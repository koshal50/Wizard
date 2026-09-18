"""Command handler: wizard explain <target>

Service function called by the TUI when the user selects "explain"
from the menu. Orchestrates the CLI pipeline:

    Step 1 -- Command Parsing:      Validate target against known targets
    Step 2 -- Intent Construction:   Build a typed Intent from parsed components
    Step 3 -- Request Assembly:      Package Intent + repo + options into InvestigationRequest
    Step 4 -- Runtime Communication: Stream events from the Runtime Engine

The explain command generates a human-readable explanation of something
the Runtime Engine already understands. Unlike investigate, it does not
actively search for new evidence. It reads from the already-verified
Claim Graph and produces a clear explanation.

Available targets:
    runtime        — How the application is expected to run
    architecture   — The design and structure of the project
    dependencies   — What dependencies the project requires
    deployment     — How the project is expected to be deployed
    security       — What security mechanisms are in place

This handler contains ZERO domain logic. It does not know what
"architecture" or "dependencies" means. It only knows how to translate
the user's selection into a structured request and stream the response.
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


def explain(
    target: str,
    repo_path: str | None = None,
    options: RequestOptions | None = None,
    intent_text: str = "",
) -> Iterator[dict]:
    """Run the explain pipeline, yielding engine events.

    Called by the TUI session when the user selects explain + target.
    Validation errors raise CommandValidationError (caller handles display).

    Args:
        target: What to explain (e.g. "runtime", "architecture"). May be empty
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
    # then validate.
    parsed = parse_intent(intent_text, "explain", menu_target=target or None)
    validate_parsed(parsed)
    validate_target("explain", parsed.targets[0])

    # Step 2: Intent Construction -- Build the Intent
    intent = build_intent(
        action="explain",
        targets=list(parsed.targets),
        urls=list(parsed.urls),
        question=intent_text,
    )

    # Step 3: Investigation Request Assembly -- Package everything
    request = InvestigationRequest(
        repository=RepositoryInfo(path=repo_path),
        intent=intent,
        options=options.for_urls(intent.urls),
    )

    # Step 4: Runtime Engine Communication -- Stream events
    yield from stream_events(request)
