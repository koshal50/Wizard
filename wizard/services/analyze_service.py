"""Analyze service — orchestrates all repository analysis scanners.

This is the main business logic layer for `wizard analyze`.
It coordinates individual scanners, aggregates results, and
reports progress.
"""

from __future__ import annotations

from pathlib import Path

from rich.progress import Progress, SpinnerColumn, TextColumn

from wizard.formatters.console import console
from wizard.models.analysis_result import AnalysisResult
from wizard.scanners import (
    config_scanner,
    framework_scanner,
    health_scanner,
    language_scanner,
    package_manager_scanner,
    repo_scanner,
    structure_scanner,
    warning_scanner,
)


def run_analysis(project_path: Path, verbose: bool = False) -> AnalysisResult:
    """Run full repository analysis.

    Executes each scanner in sequence, collecting results into
    an AnalysisResult. Errors in individual scanners are caught
    and recorded without aborting the entire analysis.

    Args:
        project_path: Validated, resolved project path.
        verbose: If True, show detailed progress.

    Returns:
        Complete AnalysisResult.
    """
    result = AnalysisResult()

    scan_steps = [
        ("Scanning repository info", _scan_repo_info),
        ("Detecting languages", _scan_languages),
        ("Detecting frameworks", _scan_frameworks),
        ("Detecting package managers", _scan_package_managers),
        ("Analyzing project structure", _scan_structure),
        ("Identifying configuration files", _scan_config_files),
        ("Evaluating repository health", _scan_health),
        ("Generating observations", _scan_warnings),
    ]

    with Progress(
        SpinnerColumn(style="bold cyan"),
        TextColumn("[bold blue]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Analyzing...", total=len(scan_steps))

        for description, scan_fn in scan_steps:
            progress.update(task, description=description)
            try:
                scan_fn(project_path, result)
            except Exception as e:
                result.errors.append(f"{description}: {e}")
            progress.advance(task)

    return result


def _scan_repo_info(project_path: Path, result: AnalysisResult) -> None:
    """Run repository information scanner."""
    result.repo_info = repo_scanner.scan(project_path)


def _scan_languages(project_path: Path, result: AnalysisResult) -> None:
    """Run language detection scanner."""
    result.languages = language_scanner.scan(project_path)
    # Populate statistics language distribution
    result.statistics.language_distribution = result.languages


def _scan_frameworks(project_path: Path, result: AnalysisResult) -> None:
    """Run framework detection scanner."""
    result.frameworks = framework_scanner.scan(project_path)


def _scan_package_managers(project_path: Path, result: AnalysisResult) -> None:
    """Run package manager detection scanner."""
    result.package_managers = package_manager_scanner.scan(project_path)


def _scan_structure(project_path: Path, result: AnalysisResult) -> None:
    """Run structure analysis scanner."""
    structure, statistics = structure_scanner.scan(project_path)
    result.structure = structure
    # Merge statistics (preserve language distribution from earlier scan)
    lang_dist = result.statistics.language_distribution
    result.statistics = statistics
    result.statistics.language_distribution = lang_dist


def _scan_config_files(project_path: Path, result: AnalysisResult) -> None:
    """Run configuration file scanner."""
    result.config_files = config_scanner.scan(project_path)


def _scan_health(project_path: Path, result: AnalysisResult) -> None:
    """Run repository health scanner."""
    result.health_checks = health_scanner.scan(project_path)


def _scan_warnings(project_path: Path, result: AnalysisResult) -> None:
    """Run warning generation scanner (depends on prior results)."""
    result.warnings = warning_scanner.scan(project_path, result)
