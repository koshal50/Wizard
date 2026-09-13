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
) -> Iterator[dict]:
    """Run the investigate pipeline, yielding engine events.

    Called by the TUI session when the user selects investigate + target.
    Validation errors raise CommandValidationError (caller handles display).

    Args:
        target: What to investigate (e.g. "architecture", "security").
        repo_path: Absolute path to the repository. Defaults to cwd.
        options: Execution options. Defaults to RequestOptions().

    Yields:
        Engine event dicts from stream_events().
    """
    repo_path = repo_path or os.getcwd()
    options = options or RequestOptions()

    # Step 1: Command Parsing — Validate the target
    validate_target("investigate", target)

    # Step 2: Intent Construction — Build the Intent
    intent = build_intent(action="investigate", target=target)

    # Step 3: Investigation Request Assembly — Package everything
    request = InvestigationRequest(
        repository=RepositoryInfo(path=repo_path),
        intent=intent,
        options=options,
    )

    # Step 4: Runtime Engine Communication — Stream events
    yield from stream_events(request)
