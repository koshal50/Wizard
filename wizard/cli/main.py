"""Wizard CLI — Entry Point.

Creates the Typer application and registers the global --version option.
The only behaviour is opening the interactive TUI when the user runs
bare `wizard`. All command families (investigate, verify, report, explain)
are selected from the TUI menu using keyboard navigation.

This is the single entry point. No subcommands are registered — the TUI
owns the full-screen experience.
"""

from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console

from wizard import __version__


# ---------------------------------------------------------------------------
# Console for styled output (version display only)
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
        "for the Runtime Engine.\n\n"
        "Run with no arguments to open the interactive Wizard interface."
    ),
    no_args_is_help=False,
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


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
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

    Run with no command to open the interactive Wizard interface.
    """
    # Bare `wizard` (no --version) opens the interactive TUI.
    if ctx.invoked_subcommand is None:
        from wizard.cli.tui import run_tui

        run_tui()


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------
def main() -> None:
    """Main entry point for the Wizard CLI."""
    app()
