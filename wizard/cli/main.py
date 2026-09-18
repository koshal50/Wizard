"""Wizard CLI — Entry Point.

Creates the Typer application and registers the global --version option.
The only behaviour is opening the interactive TUI when the user runs
bare `wizard`. All command families (investigate, verify, report, explain)
are selected from the TUI menu using keyboard navigation.

This is the single entry point. No subcommands are registered — the TUI
owns the full-screen experience.
"""

from __future__ import annotations

import sys
from typing import Optional

import typer
from rich.console import Console

from wizard import __version__


def _force_utf8_streams() -> None:
    """Make stdout/stderr tolerate any character the UI prints.

    Windows consoles default to a legacy code page (cp1252 here), and a single
    unencodable character raises UnicodeEncodeError and kills the process —
    which is what happened the first time the service report printed its status
    glyphs. Reconfiguring to UTF-8 fixes it properly; `errors="replace"` is the
    floor for the case where the console genuinely cannot render a character,
    so the worst outcome is a mangled glyph rather than a crashed CLI.

    Guarded because `reconfigure` only exists on TextIOWrapper, and a caller
    may have replaced the streams (pytest's capture, a pipe, a wrapper).
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass  # a stream that refuses to be reconfigured still works


_force_utf8_streams()


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
    path: Optional[str] = typer.Argument(
        None,
        help=(
            "The project to investigate. Defaults to the current directory. "
            "Accepts a relative or absolute folder path."
        ),
        metavar="[PROJECT]",
    ),
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

    Run with no command to open the interactive Wizard interface, optionally
    naming the project to investigate: `wizard C:/path/to/project`.
    """
    # Bare `wizard` (no --version) opens the interactive TUI.
    if ctx.invoked_subcommand is None:
        from wizard.cli.tui import run_tui

        run_tui(path)


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------
def main() -> None:
    """Main entry point for the Wizard CLI."""
    app()
