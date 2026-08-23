"""Progress display — Step 5 of the CLI pipeline.

Displays real-time progress while the Runtime Engine processes the request.

CURRENT STATE: The Runtime Engine does not exist yet, so there is no
progress stream to display. This module provides a simulated progress
display that shows the request was sent and is being "processed."

When the Runtime Engine is built, this module will poll a progress
endpoint and render live updates:
    - Knowledge Discovery status
    - Goal tracking (in progress / waiting / complete)
    - Observation count
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from wizard.cli.models.investigation_request import InvestigationRequest

console = Console()


def show_progress(request: InvestigationRequest) -> None:
    """Display investigation progress to the user.

    Currently shows a static "sent to Runtime Engine" message since
    the engine does not exist yet. Will be replaced with live polling
    when the Runtime Engine API is available.

    Args:
        request: The InvestigationRequest that was sent.
    """
    target_label = ", ".join(request.intent.targets) if request.intent.targets else "all"
    action_label = request.intent.action.capitalize()

    # Build the header
    header = Text()
    header.append("Wizard", style="bold magenta")
    header.append(" -- ", style="dim")
    header.append(f"{action_label}", style="bold cyan")
    header.append(f" {target_label}", style="bold white")

    # Build the body
    body = Text()
    body.append("Repository: ", style="dim")
    body.append(f"{request.repository.path}\n", style="white")
    body.append("Budget:     ", style="dim")
    body.append(f"{request.options.budget} operations\n", style="white")
    body.append("Format:     ", style="dim")
    body.append(f"{request.options.output_format}\n\n", style="white")
    body.append(">> Sending request to Runtime Engine...", style="yellow")

    panel = Panel(
        body,
        title=header,
        border_style="magenta",
        padding=(1, 2),
    )

    if not request.options.quiet:
        console.print()
        console.print(panel)
