"""Results display — Step 6 of the CLI pipeline.

Renders the RuntimeResponse to the terminal after the investigation completes.

CURRENT STATE: Since the Runtime Engine is a stub, results display shows
the acknowledgement and the full request payload (useful for validating
the pipeline works correctly).

When the Runtime Engine is built, this module will render:
    - Goal verdicts (verified / failed / uncertain)
    - Key findings
    - Report save location
"""

from __future__ import annotations

import json

from rich.console import Console
from rich.json import JSON
from rich.panel import Panel
from rich.text import Text

from wizard.cli.runtime_client.client import RuntimeResponse

console = Console()


def show_results(response: RuntimeResponse, *, verbose: bool = False) -> None:
    """Display investigation results to the user.

    Args:
        response: The RuntimeResponse from the Runtime Engine.
        verbose: If True, show the full request payload.
    """
    # Status styling
    status_styles = {
        "accepted": ("+", "green"),
        "completed": ("+", "bold green"),
        "in_progress": ("*", "yellow"),
        "failed": ("x", "bold red"),
        "engine_unavailable": ("x", "red"),
    }
    icon, style = status_styles.get(response.status, ("?", "dim"))

    # Build the result header
    header = Text()
    header.append("Wizard", style="bold magenta")
    header.append(" -- ", style="dim")
    header.append("Response", style="bold white")

    # Build the body
    body = Text()
    body.append(f" {icon} ", style=style)
    body.append(f"Status: ", style="dim")
    body.append(f"{response.status.upper()}\n\n", style=f"bold {style}")
    body.append(response.message, style="white")

    # Show the note from stub engine
    if "note" in response.data:
        body.append("\n\n")
        body.append("[i] ", style="blue")
        body.append(response.data["note"], style="dim italic")

    panel = Panel(
        body,
        title=header,
        border_style="green" if response.status in ("accepted", "completed") else "red",
        padding=(1, 2),
    )

    console.print()
    console.print(panel)

    # Verbose mode: show the full serialized request
    if verbose and "request" in response.data:
        request_json = json.dumps(response.data["request"], indent=2)
        console.print()
        console.print(
            Panel(
                JSON(request_json),
                title=Text("Investigation Request Payload", style="bold cyan"),
                border_style="cyan",
                padding=(1, 2),
            )
        )

    console.print()
