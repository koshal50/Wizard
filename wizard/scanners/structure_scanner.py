"""Project structure scanner.

Summarizes directories, files, source files, documentation, configuration,
templates, static assets, and tests.
"""

from __future__ import annotations

from pathlib import Path

from wizard.models.analysis_result import ProjectStructure, RepoStatistics
from wizard.utils.constants import (
    DOC_DIRS,
    DOC_EXTENSIONS,
    EXTENSION_LANGUAGE_MAP,
    SOURCE_LANGUAGES,
    STATIC_DIRS,
    STATIC_EXTENSIONS,
    TEMPLATE_DIRS,
    TEMPLATE_EXTENSIONS,
    TEST_DIRS,
    CONFIG_FILES,
)
from wizard.utils.file_utils import (
    format_file_size,
    get_file_size,
    walk_directories,
    walk_project,
)


def scan(project_path: Path) -> tuple[ProjectStructure, RepoStatistics]:
    """Scan project structure and gather statistics.

    Args:
        project_path: Resolved path to the project root.

    Returns:
        Tuple of (ProjectStructure, RepoStatistics).
    """
    files = walk_project(project_path)
    dirs = walk_directories(project_path)

    structure = _categorize_files(project_path, files)
    statistics = _compute_statistics(project_path, files, dirs)

    return structure, statistics


def _categorize_files(project_path: Path, files: list[Path]) -> ProjectStructure:
    """Categorize all project files into structure groups."""
    structure = ProjectStructure()
    structure.total_files = len(files)

    seen_dirs: set[str] = set()

    for file_path in files:
        ext = file_path.suffix.lower()
        rel_parts = file_path.relative_to(project_path).parts
        parent_names = {p.lower() for p in rel_parts[:-1]}

        # Count unique directories
        if len(rel_parts) > 1:
            parent_dir = str(file_path.parent)
            if parent_dir not in seen_dirs:
                seen_dirs.add(parent_dir)

        # Source files
        lang = EXTENSION_LANGUAGE_MAP.get(ext)
        if lang and lang in SOURCE_LANGUAGES:
            structure.source_files += 1

            # Test files (source files in test directories)
            if parent_names & TEST_DIRS or file_path.name.startswith("test_") or file_path.name.endswith("_test.py"):
                structure.test_files += 1
            continue

        # Documentation files
        if ext in DOC_EXTENSIONS and (parent_names & DOC_DIRS or file_path.name.upper().startswith("README")):
            structure.documentation_files += 1
            continue

        # Configuration files
        if file_path.name in CONFIG_FILES:
            structure.configuration_files += 1
            continue

        # Template files
        if ext in TEMPLATE_EXTENSIONS or parent_names & TEMPLATE_DIRS:
            structure.template_files += 1
            continue

        # Static assets
        if ext in STATIC_EXTENSIONS or parent_names & STATIC_DIRS:
            structure.static_assets += 1
            continue

    structure.total_directories = len(seen_dirs)

    return structure


def _compute_statistics(
    project_path: Path,
    files: list[Path],
    dirs: list[Path],
) -> RepoStatistics:
    """Compute aggregate repository statistics."""
    total_size = sum(get_file_size(f) for f in files)

    # Source file count
    source_count = sum(
        1 for f in files
        if EXTENSION_LANGUAGE_MAP.get(f.suffix.lower()) in SOURCE_LANGUAGES
    )

    # Largest directories (by file count)
    dir_file_counts: dict[str, int] = {}
    for f in files:
        try:
            parent = str(f.parent.relative_to(project_path))
            if parent == ".":
                parent = "(root)"
            dir_file_counts[parent] = dir_file_counts.get(parent, 0) + 1
        except ValueError:
            pass

    largest_dirs = sorted(dir_file_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    return RepoStatistics(
        total_files=len(files),
        total_directories=len(dirs),
        source_file_count=source_count,
        total_size_bytes=total_size,
        largest_directories=largest_dirs,
    )
