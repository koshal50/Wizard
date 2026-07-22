"""Wizard CLI — Entry Point.

Creates the Typer application, registers global options, and
registers all command families.

This is the only file that knows about all command families.
Individual command handlers are imported and registered here.
"""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console

from wizard import __version__
from wizard.cli.commands.investigate import investigate
from wizard.cli.commands.verify import verify


# ---------------------------------------------------------------------------
# Console for styled output
# ---------------------------------------------------------------------------
console = Console()


# ---------------------------------------------------------------------------
# Main Typer App
# ---------------------------------------------------------------------------
app = typer.Typer(
    name="wizard",
    help=(
        "Wizard -- Intent Translation Layer.\n\n"
        "Translates user commands into structured investigation requests "
        "for the Runtime Engine."
    ),
    no_args_is_help=True,
    rich_markup_mode="rich",
    pretty_exceptions_enable=True,
    pretty_exceptions_show_locals=False,
    add_completion=False,
)


# ---------------------------------------------------------------------------
# Global Options Callback
# ---------------------------------------------------------------------------
def _version_callback(value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(
            f"[bold magenta]wizard[/bold magenta] version [bold]{__version__}[/bold]"
        )
        raise typer.Exit()


@app.callback()
def main_callback(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """Wizard -- Intent Translation Layer.

    Translate user commands into structured investigation requests
    for the Runtime Engine.
    """


# ---------------------------------------------------------------------------
# Register Command Families
# ---------------------------------------------------------------------------
# Each command family is a separate module in wizard.cli.commands/

app.command(
    name="investigate",
    help=(
        "[bold]Investigate[/bold] a specific aspect of a repository. "
        "Explores the target area and explains what it finds."
    ),
)(investigate)

app.command(
    name="verify",
    help=(
        "[bold]Verify[/bold] whether a specific aspect of a repository works correctly. "
        "Produces a confident verdict: verified, failed, or uncertain."
    ),
)(verify)


@app.command(
    name="report",
    help="[bold]Generate[/bold] a verification report. [dim](coming soon)[/dim]",
)
def report_stub() -> None:
    """Report command — not yet implemented."""
    console.print(
        "[yellow]The [bold]report[/bold] command is not yet implemented.[/yellow]\n"
        "[dim]It will generate reports from the Runtime Engine's verified knowledge.[/dim]"
    )
    raise typer.Exit(code=0)


@app.command(
    name="explain",
    help="[bold]Explain[/bold] something the Runtime Engine already understands. [dim](coming soon)[/dim]",
)
def explain_stub(
    target: str = typer.Argument(..., help="What to explain."),
) -> None:
    """Explain command — not yet implemented."""
    console.print(
        "[yellow]The [bold]explain[/bold] command is not yet implemented.[/yellow]\n"
        "[dim]It will read from the verified Claim Graph and produce explanations.[/dim]"
    )
    raise typer.Exit(code=0)


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------
def main() -> None:
    """Main entry point for the Wizard CLI."""
    app()
