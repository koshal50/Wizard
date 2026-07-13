"""CLI command: wizard dependency-insights

Thin wrapper — validates input, calls the dependency service,
and delegates formatting. No business logic here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from wizard.cli.config import load_config
from wizard.formatters.console import console, print_banner, print_error


def dependency_insights(
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
    json_output: bool = typer.Option(
        False,
        "--json",
        "-j",
        help="Output results as JSON.",
    ),
    graph: bool = typer.Option(
        False,
        "--graph",
        "-g",
        help="Show text-based dependency relationship tree.",
    ),
    no_banner: bool = typer.Option(
        False,
        "--no-banner",
        help="Suppress the Wizard banner.",
    ),
) -> None:
    """Analyze dependency manifests and provide usage insights.

    Examples:
        wizard dependency-insights .
        wizard dependency-insights ./backend --summary
        wizard dependency-insights . --json
        wizard dependency-insights . --graph
    """
    # Load config and apply defaults
    config = load_config(project_path)
    if config.get("summary_mode") and not summary:
        summary = config["summary_mode"]
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

    # Run dependency analysis
    from wizard.services.dependency_service import run_dependency_analysis

    try:
        result = run_dependency_analysis(resolved_path)
    except Exception as e:
        print_error(f"Dependency analysis failed: {e}")
        raise typer.Exit(code=1)

    # Check if any manifests were found
    if not result.manifest_files:
        from wizard.formatters.console import print_warning
        print_warning("No dependency manifests found in this project.")
        print_info_msg = (
            "Supported manifests: requirements.txt, pyproject.toml, "
            "package.json, pom.xml, build.gradle, Cargo.toml"
        )
        from wizard.formatters.console import print_info
        print_info(print_info_msg)
        raise typer.Exit(code=0)

    # Format output
    if json_output:
        from wizard.formatters.json_formatter import format_as_json
        format_as_json(result)
    else:
        from wizard.formatters.dependency_formatter import format_dependencies
        format_dependencies(result, summary=summary, show_graph=graph)
