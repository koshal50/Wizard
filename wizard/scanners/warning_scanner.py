"""Non-invasive warning generation scanner.

Generates informative observations about the repository without
being critical or blocking.
"""

from __future__ import annotations

from pathlib import Path

from wizard.models.analysis_result import (
    AnalysisResult,
    Warning,
)
from wizard.utils.constants import (
    DOC_DIRS,
    LARGE_FILE_SIZE_THRESHOLD,
    LARGE_REPO_FILE_THRESHOLD,
)
from wizard.utils.file_utils import get_file_size, walk_project


def scan(project_path: Path, partial_result: AnalysisResult) -> list[Warning]:
    """Generate warnings based on previously collected analysis data.

    This scanner runs AFTER other scanners so it can use their results.

    Args:
        project_path: Resolved path to the project root.
        partial_result: Analysis results collected so far.

    Returns:
        List of Warning observations.
    """
    warnings: list[Warning] = []

    # Check health-based warnings
    _check_health_warnings(partial_result, warnings)

    # Check structure-based warnings
    _check_structure_warnings(project_path, partial_result, warnings)

    # Check for large files
    _check_large_files(project_path, warnings)

    # Check for multiple dependency manifests
    _check_multiple_manifests(partial_result, warnings)

    return warnings


def _check_health_warnings(result: AnalysisResult, warnings: list[Warning]) -> None:
    """Generate warnings from health check failures."""
    for check in result.health_checks:
        if not check.passed:
            if check.check_id == "readme":
                warnings.append(Warning(
                    severity="warning",
                    category="documentation",
                    message="README file is missing. A README helps others understand your project.",
                ))
            elif check.check_id == "license":
                warnings.append(Warning(
                    severity="warning",
                    category="legal",
                    message="LICENSE file is missing. Consider adding a license to clarify usage rights.",
                ))
            elif check.check_id == "tests":
                warnings.append(Warning(
                    severity="info",
                    category="testing",
                    message="No test directory detected. Consider adding tests to improve code quality.",
                ))
            elif check.check_id == "gitignore":
                warnings.append(Warning(
                    severity="suggestion",
                    category="git",
                    message="No .gitignore file found. This may lead to committing unwanted files.",
                ))


def _check_structure_warnings(
    project_path: Path,
    result: AnalysisResult,
    warnings: list[Warning],
) -> None:
    """Generate warnings from structure analysis."""
    # Very large repository
    if result.statistics.total_files > LARGE_REPO_FILE_THRESHOLD:
        warnings.append(Warning(
            severity="info",
            category="structure",
            message=f"Very large repository detected ({result.statistics.total_files:,} files). Analysis may be slow.",
        ))

    # Empty documentation directory
    for doc_dir_name in DOC_DIRS:
        doc_dir = project_path / doc_dir_name
        if doc_dir.is_dir():
            try:
                contents = list(doc_dir.iterdir())
                if not contents:
                    warnings.append(Warning(
                        severity="suggestion",
                        category="documentation",
                        message=f"Documentation directory '{doc_dir_name}/' exists but is empty.",
                    ))
            except PermissionError:
                pass

    # No source files detected
    if result.structure.source_files == 0:
        warnings.append(Warning(
            severity="info",
            category="structure",
            message="No source code files detected. This might be a configuration-only repository.",
        ))


def _check_large_files(project_path: Path, warnings: list[Warning]) -> None:
    """Detect large files that might be generated or binary."""
    files = walk_project(project_path)

    large_files: list[tuple[str, int]] = []
    for f in files:
        size = get_file_size(f)
        if size > LARGE_FILE_SIZE_THRESHOLD:
            try:
                rel = str(f.relative_to(project_path))
            except ValueError:
                rel = str(f)
            large_files.append((rel, size))

    if large_files:
        large_files.sort(key=lambda x: x[1], reverse=True)
        for name, size in large_files[:5]:  # Report top 5
            size_mb = size / 1_048_576
            warnings.append(Warning(
                severity="info",
                category="structure",
                message=f"Large file detected: {name} ({size_mb:.1f} MB). Consider if this should be tracked in version control.",
            ))


def _check_multiple_manifests(result: AnalysisResult, warnings: list[Warning]) -> None:
    """Warn about multiple dependency manifests for the same ecosystem."""
    ecosystem_pms: dict[str, list[str]] = {}
    for pm in result.package_managers:
        ecosystem_pms.setdefault(pm.ecosystem, []).append(pm.name)

    for ecosystem, pms in ecosystem_pms.items():
        if len(pms) > 1:
            pm_list = ", ".join(pms)
            warnings.append(Warning(
                severity="info",
                category="dependencies",
                message=f"Multiple {ecosystem} package managers detected: {pm_list}. This might cause confusion.",
            ))
