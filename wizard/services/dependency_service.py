"""Dependency insights service — orchestrates dependency analysis.

This is the main business logic layer for `wizard dependency-insights`.
It detects manifests, parses dependencies, and runs analyzers.
"""

from __future__ import annotations

from pathlib import Path

from rich.progress import Progress, SpinnerColumn, TextColumn

from wizard.analyzers import (
    duplicate_analyzer,
    import_analyzer,
    manifest_validator,
    missing_analyzer,
    unused_analyzer,
)
from wizard.formatters.console import console
from wizard.models.dependency_result import DependencyRelationship, DependencyResult
from wizard.parsers.base_parser import BaseParser
from wizard.parsers.java_parser import JavaParser
from wizard.parsers.node_parser import NodeParser
from wizard.parsers.python_parser import PythonParser
from wizard.parsers.rust_parser import RustParser
from wizard.utils.file_utils import safe_read_file


# Registry of all parsers
ALL_PARSERS: list[BaseParser] = [
    PythonParser(),
    NodeParser(),
    JavaParser(),
    RustParser(),
]


def run_dependency_analysis(project_path: Path) -> DependencyResult:
    """Run full dependency analysis.

    Args:
        project_path: Validated, resolved project path.

    Returns:
        Complete DependencyResult.
    """
    result = DependencyResult()

    steps = [
        ("Detecting dependency manifests", _detect_manifests),
        ("Parsing dependencies", _parse_dependencies),
        ("Checking for duplicates", _check_duplicates),
        ("Analyzing imports", _analyze_imports),
        ("Finding unused dependencies", _find_unused),
        ("Finding missing dependencies", _find_missing),
        ("Validating manifests", _validate_manifests),
        ("Building dependency relationships", _build_relationships),
    ]

    with Progress(
        SpinnerColumn(style="bold cyan"),
        TextColumn("[bold blue]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Analyzing dependencies...", total=len(steps))

        for description, step_fn in steps:
            progress.update(task, description=description)
            try:
                step_fn(project_path, result)
            except Exception as e:
                result.errors.append(f"{description}: {e}")
            progress.advance(task)

    return result


def _detect_manifests(project_path: Path, result: DependencyResult) -> None:
    """Detect all dependency manifest files in the project."""
    manifest_files: list[str] = []
    ecosystem: str | None = None
    package_manager: str | None = None

    # Known manifest filenames and their ecosystem/manager
    manifest_map = {
        "requirements.txt": ("Python", "pip"),
        "pyproject.toml": ("Python", "pip/Poetry"),
        "Pipfile": ("Python", "Pipenv"),
        "poetry.lock": ("Python", "Poetry"),
        "package.json": ("Node.js", "npm"),
        "pom.xml": ("Java", "Maven"),
        "build.gradle": ("Java", "Gradle"),
        "build.gradle.kts": ("Java", "Gradle"),
        "Cargo.toml": ("Rust", "Cargo"),
    }

    for filename, (eco, pm) in manifest_map.items():
        candidate = project_path / filename
        if candidate.is_file():
            manifest_files.append(filename)
            if ecosystem is None:
                ecosystem = eco
                package_manager = pm

    # Check for requirements/*.txt
    req_dir = project_path / "requirements"
    if req_dir.is_dir():
        try:
            for f in sorted(req_dir.iterdir()):
                if f.is_file() and f.suffix == ".txt":
                    rel = f"requirements/{f.name}"
                    manifest_files.append(rel)
                    if ecosystem is None:
                        ecosystem = "Python"
                        package_manager = "pip"
        except PermissionError:
            pass

    result.manifest_files = manifest_files
    result.ecosystem = ecosystem
    result.package_manager = package_manager


def _parse_dependencies(project_path: Path, result: DependencyResult) -> None:
    """Parse all detected manifest files for dependencies."""
    for manifest_rel in result.manifest_files:
        manifest_path = project_path / manifest_rel
        if not manifest_path.is_file():
            continue

        for parser in ALL_PARSERS:
            if parser.can_parse(manifest_path.name):
                try:
                    deps = parser.parse(manifest_path)
                    result.dependencies.extend(deps)
                except Exception as e:
                    result.errors.append(f"Error parsing {manifest_rel}: {e}")
                break


def _check_duplicates(project_path: Path, result: DependencyResult) -> None:
    """Run duplicate dependency detection."""
    result.duplicates = duplicate_analyzer.analyze(result.dependencies)


def _analyze_imports(project_path: Path, result: DependencyResult) -> None:
    """Extract imports from source files (stored in result for later use)."""
    # Store imports in a temporary attribute for use by unused/missing analyzers
    result._project_imports = import_analyzer.extract_imports(project_path)  # type: ignore[attr-defined]


def _find_unused(project_path: Path, result: DependencyResult) -> None:
    """Run unused dependency heuristic analysis."""
    imports = getattr(result, "_project_imports", {})
    result.unused_hints = unused_analyzer.analyze(result.dependencies, imports)


def _find_missing(project_path: Path, result: DependencyResult) -> None:
    """Run missing dependency heuristic analysis."""
    imports = getattr(result, "_project_imports", {})
    result.missing_hints = missing_analyzer.analyze(result.dependencies, imports)


def _validate_manifests(project_path: Path, result: DependencyResult) -> None:
    """Run manifest validation."""
    manifest_paths = [project_path / rel for rel in result.manifest_files]
    result.manifest_issues = manifest_validator.validate_manifests(manifest_paths)


def _build_relationships(project_path: Path, result: DependencyResult) -> None:
    """Build simple dependency relationship overview.

    Only direct dependencies are available without package installation.
    Transitive dependencies cannot be resolved locally.
    """
    # Group dependencies by source file for relationship overview
    by_file: dict[str, list[str]] = {}
    for dep in result.dependencies:
        by_file.setdefault(dep.source_file, []).append(dep.name)

    for source_file, dep_names in by_file.items():
        for dep_name in dep_names:
            result.relationships.append(
                DependencyRelationship(
                    package=dep_name,
                    depends_on=[],  # Cannot resolve without installation
                    relationship_type="direct",
                )
            )
