"""Manifest validation analyzer.

Checks dependency manifest files for common structural issues.
"""

from __future__ import annotations

from pathlib import Path

from wizard.models.dependency_result import ManifestIssue
from wizard.parsers.base_parser import BaseParser
from wizard.parsers.java_parser import JavaParser
from wizard.parsers.node_parser import NodeParser
from wizard.parsers.python_parser import PythonParser
from wizard.parsers.rust_parser import RustParser


# All available parsers
ALL_PARSERS: list[BaseParser] = [
    PythonParser(),
    NodeParser(),
    JavaParser(),
    RustParser(),
]


def validate_manifests(manifest_files: list[Path]) -> list[ManifestIssue]:
    """Validate all detected manifest files.

    Args:
        manifest_files: List of manifest file Paths.

    Returns:
        List of ManifestIssue findings.
    """
    issues: list[ManifestIssue] = []

    for manifest_path in manifest_files:
        for parser in ALL_PARSERS:
            if parser.can_parse(manifest_path.name):
                try:
                    file_issues = parser.validate(manifest_path)
                    issues.extend(file_issues)
                except Exception as e:
                    issues.append(ManifestIssue(
                        file=manifest_path.name,
                        issue_type="error",
                        message=f"Validation failed: {e}",
                        severity="error",
                    ))
                break  # Only validate with the first matching parser

    return issues
