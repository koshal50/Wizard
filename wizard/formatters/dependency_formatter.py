"""Rich output formatter for `wizard dependency-insights` results.

Renders dependency analysis results with tables, panels, and
styled text for a premium terminal experience.
All text is ASCII-safe for cross-platform compatibility.
"""

from __future__ import annotations

from rich import box
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from wizard.formatters.console import (
    ICON_CHECK,
    ICON_CROSS,
    ICON_INFO,
    ICON_WARN,
    SEC_DEPS_DUP,
    SEC_DEPS_ISSUES,
    SEC_DEPS_LIST,
    SEC_DEPS_MISSING,
    SEC_DEPS_OVERVIEW,
    SEC_DEPS_TREE,
    SEC_DEPS_UNUSED,
    console,
    print_bullet,
    print_header,
    print_info,
    print_key_value,
    print_section,
    print_warning,
)
from wizard.models.dependency_result import DependencyGroup, DependencyResult


def format_dependencies(
    result: DependencyResult,
    summary: bool = False,
    show_graph: bool = False,
) -> None:
    """Render dependency analysis results to the terminal.

    Args:
        result: Complete dependency analysis result.
        summary: If True, show condensed output.
        show_graph: If True, show text-based dependency tree.
    """
    if summary:
        _format_summary_mode(result)
        return

    _format_overview(result)
    _format_dependency_table(result)
    _format_duplicates(result)
    _format_unused(result)
    _format_missing(result)
    _format_manifest_issues(result)

    if show_graph:
        _format_dependency_graph(result)

    _format_final_summary(result)

    if result.errors:
        _format_errors(result)


def _format_overview(result: DependencyResult) -> None:
    """Render dependency overview."""
    print_header(SEC_DEPS_OVERVIEW)

    if result.package_manager:
        print_key_value("Package Manager", f"[bold]{result.package_manager}[/]")
    if result.ecosystem:
        print_key_value("Ecosystem", result.ecosystem)
    if result.manifest_files:
        print_key_value("Manifests", ", ".join(result.manifest_files))

    print_key_value("Total Dependencies", f"[wizard.number]{result.total_dependencies}[/]")

    # Show distribution
    groups = result.dependencies_by_group
    if groups:
        print_section("Distribution")
        group_icons = {
            "production": "[wizard.info]o[/]",
            "development": "[wizard.warning]o[/]",
            "testing": "[wizard.success]o[/]",
            "optional": "[wizard.muted]o[/]",
            "build": "[wizard.accent]o[/]",
            "peer": "[wizard.brand]o[/]",
            "unknown": "[wizard.dim]o[/]",
        }
        for group_name, deps in sorted(groups.items()):
            icon = group_icons.get(group_name, "-")
            print_bullet(
                f"{icon} [bold]{group_name.title()}:[/] "
                f"[wizard.number]{len(deps)}[/] packages"
            )


def _format_dependency_table(result: DependencyResult) -> None:
    """Render dependency list as a table."""
    if not result.dependencies:
        return

    print_header(SEC_DEPS_LIST)

    # Group by category
    groups = result.dependencies_by_group

    for group_name, deps in sorted(groups.items()):
        group_style = {
            "production": "wizard.success",
            "development": "wizard.warning",
            "testing": "wizard.info",
            "optional": "wizard.muted",
            "build": "wizard.accent",
        }.get(group_name, "wizard.muted")

        table = Table(
            title=f"[{group_style}]{group_name.title()}[/]",
            box=box.ROUNDED,
            border_style="wizard.muted",
            show_header=True,
            header_style="wizard.label",
            padding=(0, 1),
            expand=True,
        )
        table.add_column("Package", style="bold", min_width=20)
        table.add_column("Version", style="wizard.number", min_width=12)
        table.add_column("Source", style="wizard.dim")

        for dep in sorted(deps, key=lambda d: d.name.lower()):
            extras = f" [{', '.join(dep.extras)}]" if dep.extras else ""
            table.add_row(
                f"{dep.name}{extras}",
                dep.version_constraint,
                dep.source_file,
            )

        console.print()
        console.print(table)


def _format_duplicates(result: DependencyResult) -> None:
    """Render duplicate dependency findings."""
    if not result.duplicates:
        return

    print_header(f"{SEC_DEPS_DUP} ({len(result.duplicates)})")

    for dup in result.duplicates:
        conflict_tag = " [wizard.error][CONFLICT][/]" if dup.has_conflict else ""
        console.print(f"    [bold]{dup.name}[/]{conflict_tag}")
        for loc in dup.locations:
            console.print(f"      [wizard.dim]`-- {loc}[/]")
        if dup.has_conflict:
            versions_str = " vs ".join(dup.versions)
            console.print(f"      [wizard.warning]Versions: {versions_str}[/]")


def _format_unused(result: DependencyResult) -> None:
    """Render potentially unused dependencies."""
    if not result.unused_hints:
        return

    print_header(f"{SEC_DEPS_UNUSED} ({len(result.unused_hints)})")
    console.print(
        "    [wizard.dim]! Heuristic analysis -- these may be used indirectly[/]"
    )
    console.print()

    for hint in result.unused_hints:
        confidence_color = {
            "high": "wizard.error",
            "medium": "wizard.warning",
            "low": "wizard.muted",
        }.get(hint.confidence, "wizard.muted")

        console.print(
            f"    [bold]{hint.name}[/]  "
            f"[{confidence_color}]({hint.confidence})[/]  "
            f"[wizard.dim]{hint.declared_in}[/]"
        )
        if hint.note:
            console.print(f"      [wizard.dim]> {hint.note}[/]")


def _format_missing(result: DependencyResult) -> None:
    """Render potentially missing dependencies."""
    if not result.missing_hints:
        return

    print_header(f"{SEC_DEPS_MISSING} ({len(result.missing_hints)})")
    console.print(
        "    [wizard.dim]! Suggestions based on import analysis -- verify before adding[/]"
    )
    console.print()

    for hint in result.missing_hints:
        confidence_color = {
            "high": "wizard.error",
            "medium": "wizard.warning",
            "low": "wizard.muted",
        }.get(hint.confidence, "wizard.muted")

        suggested = f" -> [wizard.tag]{hint.suggested_package}[/]" if hint.suggested_package and hint.suggested_package != hint.import_name else ""
        console.print(
            f"    [bold]{hint.import_name}[/]{suggested}  "
            f"[{confidence_color}]({hint.confidence})[/]"
        )


def _format_manifest_issues(result: DependencyResult) -> None:
    """Render manifest validation issues."""
    if not result.manifest_issues:
        return

    print_header(f"{SEC_DEPS_ISSUES} ({len(result.manifest_issues)})")

    for issue in result.manifest_issues:
        if issue.severity == "error":
            icon = ICON_CROSS
        elif issue.severity == "warning":
            icon = ICON_WARN
        else:
            icon = ICON_INFO

        line_info = f" (line {issue.line_number})" if issue.line_number else ""
        console.print(f"    {icon} [bold]{issue.file}[/]{line_info}: {issue.message}")


def _format_dependency_graph(result: DependencyResult) -> None:
    """Render a text-based dependency relationship tree."""
    if not result.dependencies:
        return

    print_header(SEC_DEPS_TREE)
    console.print(
        "    [wizard.dim]Note: Only direct dependencies are shown. "
        "Transitive dependencies require package installation to resolve.[/]"
    )

    # Group by source file
    by_source: dict[str, list[str]] = {}
    for dep in result.dependencies:
        by_source.setdefault(dep.source_file, []).append(dep.name)

    for source, dep_names in sorted(by_source.items()):
        tree = Tree(f"[bold]{source}[/]", guide_style="wizard.muted")
        for name in sorted(dep_names):
            tree.add(f"[wizard.value]{name}[/]")
        console.print()
        console.print(tree)


def _format_final_summary(result: DependencyResult) -> None:
    """Render the final insights summary panel."""
    lines: list[str] = []

    if result.package_manager:
        lines.append(f"[wizard.label]Package Manager:[/]    [bold]{result.package_manager}[/]")

    lines.append(f"[wizard.label]Total Dependencies:[/] [wizard.number]{result.total_dependencies}[/]")

    if result.production_count:
        lines.append(f"[wizard.label]Production:[/]         [wizard.number]{result.production_count}[/]")
    if result.dev_count:
        lines.append(f"[wizard.label]Development:[/]        [wizard.number]{result.dev_count}[/]")
    if result.test_count:
        lines.append(f"[wizard.label]Testing:[/]            [wizard.number]{result.test_count}[/]")

    if result.duplicates:
        conflicts = sum(1 for d in result.duplicates if d.has_conflict)
        dup_text = f"{len(result.duplicates)} found"
        if conflicts:
            dup_text += f" [wizard.error]({conflicts} conflicts)[/]"
        lines.append(f"[wizard.label]Duplicates:[/]         [wizard.warning]{dup_text}[/]")

    if result.unused_hints:
        lines.append(f"[wizard.label]Possibly Unused:[/]    [wizard.muted]{len(result.unused_hints)}[/]")

    if result.missing_hints:
        lines.append(f"[wizard.label]Possibly Missing:[/]   [wizard.muted]{len(result.missing_hints)}[/]")

    if result.manifest_issues:
        errors = sum(1 for i in result.manifest_issues if i.severity == "error")
        warns = sum(1 for i in result.manifest_issues if i.severity == "warning")
        issue_parts: list[str] = []
        if errors:
            issue_parts.append(f"[wizard.error]{errors} errors[/]")
        if warns:
            issue_parts.append(f"[wizard.warning]{warns} warnings[/]")
        lines.append(f"[wizard.label]Manifest Issues:[/]    {', '.join(issue_parts)}")

    summary_text = "\n".join(lines)

    console.print()
    console.print(Panel(
        summary_text,
        title="[wizard.brand]<< Dependency Insights Summary >>[/]",
        border_style="wizard.brand",
        padding=(1, 3),
        expand=True,
    ))
    console.print()


def _format_errors(result: DependencyResult) -> None:
    """Render any errors that occurred during analysis."""
    print_section("Errors")
    for error in result.errors:
        console.print(f"    {ICON_CROSS} {error}")


def _format_summary_mode(result: DependencyResult) -> None:
    """Render condensed summary output."""
    lines: list[str] = []

    if result.package_manager:
        lines.append(f"[wizard.label]Manager:[/]    {result.package_manager} ({result.ecosystem})")

    lines.append(f"[wizard.label]Total:[/]      {result.total_dependencies} dependencies")

    groups = result.dependencies_by_group
    group_parts = [f"{name.title()}: {len(deps)}" for name, deps in sorted(groups.items())]
    if group_parts:
        lines.append(f"[wizard.label]Groups:[/]     {' | '.join(group_parts)}")

    if result.duplicates:
        lines.append(f"[wizard.label]Duplicates:[/]  {len(result.duplicates)}")
    if result.unused_hints:
        lines.append(f"[wizard.label]Unused:[/]      ~{len(result.unused_hints)} (heuristic)")
    if result.missing_hints:
        lines.append(f"[wizard.label]Missing:[/]     ~{len(result.missing_hints)} (heuristic)")
    if result.manifest_issues:
        lines.append(f"[wizard.label]Issues:[/]      {len(result.manifest_issues)}")

    console.print()
    console.print(Panel(
        "\n".join(lines),
        title="[wizard.brand]<< Dependency Insights >>[/]",
        border_style="wizard.brand",
        padding=(1, 3),
        expand=True,
    ))
    console.print()
