"""Command handler: wizard report

Service function called by the TUI when the user selects "report"
from the menu. Orchestrates the existing CLI pipeline:

    Step 1 -- Command Parsing:      Validate options (no target for report)
    Step 2 -- Intent Construction:   Build a typed Intent from parsed components
    Step 3 -- Request Assembly:      Package Intent + repo + options into InvestigationRequest
    Step 4 -- Runtime Communication: Stream events from the Runtime Engine

The report command generates the final Verification Report from the
current investigation's verified knowledge.

Report output behavior:
    - The Runtime Engine generates verification_report.md in its own directory.
    - For markdown format, the CLI duplicates the report into an output/ folder
      at the project root.
    - The TUI session calls save_report() after the stream completes.

This handler contains ZERO domain logic. It does not know what a
verification report contains or how it is generated. It only knows
how to request one from the Runtime Engine and where to save the result.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterator

from wizard.cli.parser.intent_builder import build_intent
from wizard.cli.parser.intent_parser import parse_intent
from wizard.cli.models.investigation_request import (
    InvestigationRequest,
    RepositoryInfo,
    RequestOptions,
)
from wizard.cli.runtime_client.client import stream_events


def report(
    repo_path: str | None = None,
    options: RequestOptions | None = None,
    intent_text: str = "",
) -> Iterator[dict]:
    """Run the report pipeline, yielding engine events.

    Called by the TUI session when the user selects report from the menu.
    Report has no target — it generates from existing verified knowledge.
    A URL may still be typed, and is carried through: a report about a
    repository that serves a page is a report about both planes.

    Args:
        repo_path: Absolute path to the repository. Defaults to cwd.
        options: Execution options. Defaults to RequestOptions.from_env().
        intent_text: The user's free text, if any. No target is read from it —
            report accepts no command target, so named targets are dropped —
            but the URLs are carried through, and the sentence itself travels
            as `question` so the Planner can read what was asked.

    Yields:
        Engine event dicts from stream_events().
    """
    repo_path = repo_path or os.getcwd()
    options = options or RequestOptions.from_env()

    # Step 1: Command Parsing -- a URL is readable from the text; a command
    # target is not, because report accepts none (validate_target enforces it).
    parsed = parse_intent(intent_text, "report", menu_target=None)

    # Step 2: Intent Construction -- Build the Intent
    intent = build_intent(
        action="report",
        target=None,
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


def next_report_path(output_dir: Path, ext: str, *, dry_run: bool = False) -> Path:
    """Find the next available report filename in the output directory.

    Scans for existing verification_report(N) files and returns the
    next incremented path. Never overwrites.

    Args:
        output_dir: The output/ directory at the project root.
        ext: File extension (".md" or ".json").
        dry_run: If True, don't create the directory — just compute the path.

    Returns:
        Path like output/verification_report(1).md, output/verification_report(2).md, etc.
    """
    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    # Find the highest existing report number
    highest = 0
    if output_dir.exists():
        for existing in output_dir.iterdir():
            name = existing.stem  # e.g. "verification_report(3)"
            if name.startswith("verification_report(") and name.endswith(")"):
                try:
                    num = int(name[len("verification_report("):-1])
                    highest = max(highest, num)
                except ValueError:
                    continue
            elif name == "verification_report" and existing.suffix == ext:
                # Count the unnumbered one as 0
                highest = max(highest, 0)

    next_num = highest + 1
    return output_dir / f"verification_report({next_num}){ext}"


def save_report(output_path: Path, content: str) -> None:
    """Save report content to the specified file path.

    Creates parent directories if they do not exist.

    Args:
        output_path: Absolute path to the output file.
        content: The report content to write.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
