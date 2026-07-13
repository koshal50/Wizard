"""CLI command: wizard analyze

Thin wrapper — validates input, calls the analyze service,
and delegates formatting. No business logic here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from wizard.cli.config import load_config
from wizard.formatters.console import console, print_banner, print_error


def analyze(
    project_path: str = typer.Argument(
        ".",
        help="Path to the project directory to analyze.",
        show_default="current directory",
    ),
    summary: bool = typer.Option(
        False,
        "--summary",
        "-s",
        help="Show condensed summary output.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Show detailed output with additional information.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Output results as JSON.",
    ),
    no_banner: bool = typer.Option(
        False,
        "--no-banner",
        help="Suppress the Wizard banner.",
    ),
) -> None:
    """Analyze a project repository and generate a comprehensive overview.

    Examples:
        wizard analyze .
        wizard analyze ./backend
        wizard analyze /path/to/project --summary
        wizard analyze . --json
    """
    # Load config and apply defaults
    config = load_config(project_path)
    if config.get("summary_mode") and not summary:
        summary = config["summary_mode"]
    if config.get("verbose") and not verbose:
        verbose = config["verbose"]
    if config.get("default_format") == "json" and not json_output:
        json_output = True

    # Show banner (unless suppressed or JSON mode)
    show_banner = config.get("show_banner", True)
    if not json_output and not no_banner and show_banner:
        print_banner()

    # Validate path
    from wizard.utils.file_utils import validate_project_path

    try:
        resolved_path = validate_project_path(project_path)
    except FileNotFoundError:
        print_error(f"Path does not exist: {project_path}")
        raise typer.Exit(code=1)
    except NotADirectoryError:
        print_error(f"Not a directory: {project_path}")
        raise typer.Exit(code=1)
    except PermissionError:
        print_error(f"Permission denied: {project_path}")
        raise typer.Exit(code=1)

    # Run analysis
    from wizard.services.analyze_service import run_analysis

    try:
        result = run_analysis(resolved_path, verbose=verbose)
    except Exception as e:
        print_error(f"Analysis failed: {e}")
        raise typer.Exit(code=1)

    # Format output
    if json_output:
        from wizard.formatters.json_formatter import format_as_json
        format_as_json(result)
    else:
        from wizard.formatters.analyze_formatter import format_analysis
        format_analysis(result, summary=summary, verbose=verbose)
