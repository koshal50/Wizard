"""Programming language detection scanner.

Identifies languages based on file extensions and calculates distribution.
"""

from __future__ import annotations

from pathlib import Path

from wizard.models.analysis_result import LanguageInfo
from wizard.utils.constants import EXTENSION_LANGUAGE_MAP, SOURCE_LANGUAGES
from wizard.utils.file_utils import walk_project


def scan(project_path: Path) -> list[LanguageInfo]:
    """Detect programming languages used in the project.

    Args:
        project_path: Resolved path to the project root.

    Returns:
        List of LanguageInfo sorted by file count (descending).
    """
    files = walk_project(project_path)
    return _analyze_languages(files)


def _analyze_languages(files: list[Path]) -> list[LanguageInfo]:
    """Analyze file list to determine language distribution.

    Only counts languages in SOURCE_LANGUAGES for primary detection,
    but reports all detected languages.
    """
    # Count files per language
    lang_counts: dict[str, int] = {}
    lang_extensions: dict[str, set[str]] = {}

    for file_path in files:
        ext = file_path.suffix.lower()
        language = EXTENSION_LANGUAGE_MAP.get(ext)
        if language and language in SOURCE_LANGUAGES:
            lang_counts[language] = lang_counts.get(language, 0) + 1
            lang_extensions.setdefault(language, set()).add(ext)

    if not lang_counts:
        return []

    # Calculate percentages and determine primary
    total_source_files = sum(lang_counts.values())
    primary_language = max(lang_counts, key=lang_counts.get)  # type: ignore[arg-type]

    languages: list[LanguageInfo] = []
    for lang_name, count in sorted(lang_counts.items(), key=lambda x: x[1], reverse=True):
        percentage = round((count / total_source_files) * 100, 1)
        languages.append(
            LanguageInfo(
                name=lang_name,
                file_count=count,
                percentage=percentage,
                is_primary=(lang_name == primary_language),
                extensions=sorted(lang_extensions.get(lang_name, set())),
            )
        )

    return languages
