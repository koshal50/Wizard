"""Wizard CLI application definition.

Registers all commands, global options, and entry point.
"""

from __future__ import annotations

from typing import Optional

import typer

from wizard import __version__
from wizard.cli.analyze_cmd import analyze
from wizard.cli.dependency_cmd import dependency_insights
from wizard.formatters.console import console

# ---------------------------------------------------------------------------
# Main Typer App
# ---------------------------------------------------------------------------
app = typer.Typer(
    name="wizard",
    help="🧙 Wizard — Repository intelligence CLI. Analyze codebases with zero execution.",
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
        console.print(f"[wizard.brand]wizard[/] version [bold]{__version__}[/]")
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
    """🧙 Wizard — Repository Intelligence CLI."""


# ---------------------------------------------------------------------------
# Register Commands
# ---------------------------------------------------------------------------
app.command(
    name="analyze",
    help="[bold]Analyze[/] a project repository and generate a comprehensive overview.",
)(analyze)

app.command(
    name="dependency-insights",
    help="[bold]Analyze[/] project dependency manifests and provide insights.",
)(dependency_insights)


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------
def main() -> None:
    """Main entry point for the Wizard CLI."""
    app()
