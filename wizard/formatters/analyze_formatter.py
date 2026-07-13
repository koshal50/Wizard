"""Rich output formatter for `wizard analyze` results.

Renders analysis results as beautifully formatted terminal output
using Rich panels, tables, and styled text.
All text is ASCII-safe for cross-platform compatibility.
"""

from __future__ import annotations

from rich import box
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from wizard.formatters.console import (
    ICON_CHECK,
    ICON_CROSS,
    ICON_STAR,
    SEC_CONFIG,
    SEC_FRAMEWORK,
    SEC_HEALTH,
    SEC_LANG,
    SEC_PKGMGR,
    SEC_REPO,
    SEC_STATS,
    SEC_STRUCTURE,
    SEC_WARNINGS,
    console,
    print_bullet,
    print_header,
    print_info,
    print_key_value,
    print_section,
    print_success,
    print_warning,
)
from wizard.models.analysis_result import AnalysisResult
from wizard.utils.file_utils import format_file_size


def format_analysis(result: AnalysisResult, summary: bool = False, verbose: bool = False) -> None:
    """Render analysis results to the terminal.

    Args:
        result: Complete analysis result.
        summary: If True, show condensed output.
        verbose: If True, show additional detail.
    """
    if summary:
        _format_summary_mode(result)
        return

    _format_repo_info(result)
    _format_languages(result, verbose)
    _format_frameworks(result)
    _format_package_managers(result)
    _format_structure(result, verbose)
    _format_config_files(result, verbose)
    _format_health(result)
    _format_statistics(result, verbose)
    _format_warnings(result)
    _format_final_summary(result)

    if result.errors:
        _format_errors(result)


def _format_repo_info(result: AnalysisResult) -> None:
    """Render repository information section."""
    if not result.repo_info:
        return

    info = result.repo_info
    print_header(SEC_REPO)

    print_key_value("Project Name", f"[bold]{info.project_name}[/]")
    print_key_value("Root Directory", f"[wizard.path]{info.root_directory}[/]")

    if info.git_initialized:
        print_key_value("Repository Type", f"[wizard.tag]{info.repo_type or 'git'}[/]")
        if info.git_branch:
            print_key_value("Branch", info.git_branch)
        if info.git_remote_url:
            print_key_value("Remote", info.git_remote_url)
    else:
        print_key_value("Git", "[wizard.muted]Not initialized[/]")

    if info.metadata:
        for key, value in info.metadata.items():
            print_key_value(key.title(), value)


def _format_languages(result: AnalysisResult, verbose: bool) -> None:
    """Render detected languages."""
    if not result.languages:
        return

    print_header(SEC_LANG)

    table = Table(
        box=box.ROUNDED,
        border_style="wizard.muted",
        show_header=True,
        header_style="wizard.label",
        padding=(0, 2),
        expand=True,
    )
    table.add_column("Language", style="bold")
    table.add_column("Files", justify="right", style="wizard.number")
    table.add_column("Distribution", min_width=25)
    table.add_column("%", justify="right", style="wizard.number")

    for lang in result.languages:
        # Create a visual bar using ASCII blocks
        bar_length = int(lang.percentage / 100 * 25)
        bar = "#" * bar_length + "." * (25 - bar_length)

        name_text = f"{'>> ' if lang.is_primary else '   '}{lang.name}"
        bar_style = "wizard.brand" if lang.is_primary else "wizard.muted"

        table.add_row(
            name_text,
            str(lang.file_count),
            f"[{bar_style}]{bar}[/]",
            f"{lang.percentage:.1f}%",
        )

    console.print()
    console.print(table)

    if verbose:
        for lang in result.languages:
            if lang.extensions:
                console.print(f"    [wizard.muted]{lang.name}: {', '.join(lang.extensions)}[/]")


def _format_frameworks(result: AnalysisResult) -> None:
    """Render detected frameworks."""
    if not result.frameworks:
        return

    print_header(SEC_FRAMEWORK)

    for fw in result.frameworks:
        confidence_color = {
            "high": "wizard.success",
            "medium": "wizard.warning",
            "low": "wizard.muted",
        }.get(fw.confidence, "wizard.muted")

        console.print(
            f"    [bold]{fw.name}[/]  "
            f"[wizard.muted]({fw.ecosystem})[/]  "
            f"[{confidence_color}]{fw.confidence} confidence[/]"
        )


def _format_package_managers(result: AnalysisResult) -> None:
    """Render detected package managers."""
    if not result.package_managers:
        return

    print_header(SEC_PKGMGR)

    for pm in result.package_managers:
        files_str = ", ".join(pm.manifest_files) if pm.manifest_files else ""
        console.print(
            f"    [bold]{pm.name}[/]  "
            f"[wizard.muted]({pm.ecosystem})[/]  "
            f"[wizard.dim]{files_str}[/]"
        )


def _format_structure(result: AnalysisResult, verbose: bool) -> None:
    """Render project structure summary."""
    print_header(SEC_STRUCTURE)

    s = result.structure
    table = Table(
        box=box.SIMPLE,
        show_header=False,
        padding=(0, 3),
        expand=False,
    )
    table.add_column("Category", style="wizard.label")
    table.add_column("Count", justify="right", style="wizard.number")

    table.add_row("Directories", f"{s.total_directories:,}")
    table.add_row("Total Files", f"{s.total_files:,}")
    table.add_row("Source Files", f"{s.source_files:,}")
    table.add_row("Test Files", f"{s.test_files:,}")
    table.add_row("Documentation", f"{s.documentation_files:,}")
    table.add_row("Configuration", f"{s.configuration_files:,}")
    table.add_row("Templates", f"{s.template_files:,}")
    table.add_row("Static Assets", f"{s.static_assets:,}")

    console.print()
    console.print(table)


def _format_config_files(result: AnalysisResult, verbose: bool) -> None:
    """Render configuration files."""
    if not result.config_files:
        return

    if not verbose and len(result.config_files) > 15:
        print_header(f"{SEC_CONFIG} ({len(result.config_files)} detected)")
        # Group by category in compact mode
        categories: dict[str, list[str]] = {}
        for cf in result.config_files:
            categories.setdefault(cf.category, []).append(cf.name)

        for category, files in sorted(categories.items()):
            file_list = ", ".join(files[:5])
            if len(files) > 5:
                file_list += f", ... +{len(files) - 5} more"
            print_bullet(f"[wizard.label]{category}:[/] {file_list}")
        return

    print_header(SEC_CONFIG)

    table = Table(
        box=box.SIMPLE,
        show_header=True,
        header_style="wizard.label",
        padding=(0, 2),
        expand=True,
    )
    table.add_column("File", style="bold")
    table.add_column("Category", style="wizard.muted")
    table.add_column("Path", style="wizard.dim")

    for cf in result.config_files:
        table.add_row(cf.name, cf.category, cf.path)

    console.print()
    console.print(table)


def _format_health(result: AnalysisResult) -> None:
    """Render repository health checks."""
    if not result.health_checks:
        return

    score = result.health_score
    if score >= 80:
        score_style = "wizard.health.good"
        score_label = "Excellent"
    elif score >= 50:
        score_style = "wizard.health.ok"
        score_label = "Fair"
    else:
        score_style = "wizard.health.poor"
        score_label = "Needs Improvement"

    print_header(
        SEC_HEALTH,
        f"[{score_style}]{score:.0f}% -- {score_label}[/]"
    )

    for check in result.health_checks:
        icon = ICON_CHECK if check.passed else ICON_CROSS
        message_part = f"  [wizard.dim]{check.message}[/]" if check.message else ""
        console.print(f"    {icon} {check.name}{message_part}")


def _format_statistics(result: AnalysisResult, verbose: bool) -> None:
    """Render repository statistics."""
    stats = result.statistics
    print_header(SEC_STATS)

    print_key_value("Total Files", f"{stats.total_files:,}")
    print_key_value("Total Directories", f"{stats.total_directories:,}")
    print_key_value("Source Files", f"{stats.source_file_count:,}")
    print_key_value("Estimated Size", format_file_size(stats.total_size_bytes))

    if verbose and stats.largest_directories:
        print_section("Largest Directories")
        for dir_name, count in stats.largest_directories[:5]:
            print_bullet(f"{dir_name} -- [wizard.number]{count}[/] files")


def _format_warnings(result: AnalysisResult) -> None:
    """Render warnings and observations."""
    if not result.warnings:
        return

    print_header(f"{SEC_WARNINGS} ({len(result.warnings)})")

    for warning in result.warnings:
        if warning.severity == "warning":
            print_warning(warning.message)
        elif warning.severity == "info":
            print_info(warning.message)
        else:
            print_bullet(f"[wizard.muted]{warning.message}[/]")


def _format_final_summary(result: AnalysisResult) -> None:
    """Render the final summary panel."""
    summary_lines: list[str] = []

    # Technologies
    if result.languages:
        primary = result.primary_language or "Unknown"
        lang_count = len(result.languages)
        summary_lines.append(f"[wizard.label]Primary Language:[/]  [bold]{primary}[/]  [wizard.muted]({lang_count} detected)[/]")

    if result.frameworks:
        fw_names = ", ".join(fw.name for fw in result.frameworks)
        summary_lines.append(f"[wizard.label]Frameworks:[/]        [bold]{fw_names}[/]")

    if result.package_managers:
        pm_names = ", ".join(pm.name for pm in result.package_managers)
        summary_lines.append(f"[wizard.label]Package Managers:[/]  [bold]{pm_names}[/]")

    # Health
    score = result.health_score
    if score >= 80:
        score_style = "wizard.health.good"
    elif score >= 50:
        score_style = "wizard.health.ok"
    else:
        score_style = "wizard.health.poor"
    summary_lines.append(f"[wizard.label]Health Score:[/]      [{score_style}]{score:.0f}%[/]")

    # Stats
    summary_lines.append(
        f"[wizard.label]Files:[/]             [wizard.number]{result.statistics.total_files:,}[/]  "
        f"[wizard.label]Size:[/] [wizard.number]{format_file_size(result.statistics.total_size_bytes)}[/]"
    )

    if result.warnings:
        summary_lines.append(f"[wizard.label]Observations:[/]     [wizard.warning]{len(result.warnings)}[/]")

    summary_text = "\n".join(summary_lines)

    console.print()
    console.print(Panel(
        summary_text,
        title="[wizard.brand]<< Analysis Summary >>[/]",
        border_style="wizard.brand",
        padding=(1, 3),
        expand=True,
    ))
    console.print()


def _format_errors(result: AnalysisResult) -> None:
    """Render any errors that occurred during analysis."""
    print_section("Errors")
    for error in result.errors:
        console.print(f"    {ICON_CROSS} {error}")


def _format_summary_mode(result: AnalysisResult) -> None:
    """Render a condensed single-panel summary."""
    lines: list[str] = []

    if result.repo_info:
        lines.append(f"[bold]{result.repo_info.project_name}[/]")
        lines.append(f"[wizard.path]{result.repo_info.root_directory}[/]")
        lines.append("")

    if result.languages:
        primary = result.primary_language or "Unknown"
        others = [l.name for l in result.languages if not l.is_primary][:3]
        other_str = f" + {', '.join(others)}" if others else ""
        lines.append(f"[wizard.label]Languages:[/]  {primary}{other_str}")

    if result.frameworks:
        lines.append(f"[wizard.label]Frameworks:[/] {', '.join(fw.name for fw in result.frameworks)}")

    if result.package_managers:
        lines.append(f"[wizard.label]Managers:[/]   {', '.join(pm.name for pm in result.package_managers)}")

    score = result.health_score
    health_style = "wizard.health.good" if score >= 80 else "wizard.health.ok" if score >= 50 else "wizard.health.poor"
    lines.append(f"[wizard.label]Health:[/]     [{health_style}]{score:.0f}%[/]")
    lines.append(
        f"[wizard.label]Files:[/]      {result.statistics.total_files:,}  "
        f"[wizard.label]Size:[/] {format_file_size(result.statistics.total_size_bytes)}"
    )

    if result.warnings:
        lines.append(f"[wizard.label]Warnings:[/]   {len(result.warnings)}")

    console.print()
    console.print(Panel(
        "\n".join(lines),
        title="[wizard.brand]<< Wizard Analysis >>[/]",
        border_style="wizard.brand",
        padding=(1, 3),
        expand=True,
    ))
    console.print()
