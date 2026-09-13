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
) -> Iterator[dict]:
    """Run the explain pipeline, yielding engine events.

    Called by the TUI session when the user selects explain + target.
    Validation errors raise CommandValidationError (caller handles display).

    Args:
        target: What to explain (e.g. "runtime", "architecture").
        repo_path: Absolute path to the repository. Defaults to cwd.
        options: Execution options. Defaults to RequestOptions().

    Yields:
        Engine event dicts from stream_events().
    """
    repo_path = repo_path or os.getcwd()
    options = options or RequestOptions()

    # Step 1: Command Parsing -- Validate the target
    validate_target("explain", target)

    # Step 2: Intent Construction -- Build the Intent
    intent = build_intent(action="explain", target=target)

    # Step 3: Investigation Request Assembly -- Package everything
    request = InvestigationRequest(
        repository=RepositoryInfo(path=repo_path),
        intent=intent,
        options=options,
    )

    # Step 4: Runtime Engine Communication -- Stream events
    yield from stream_events(request)
