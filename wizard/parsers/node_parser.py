"""Node.js dependency manifest parser.

Handles: package.json
"""

from __future__ import annotations

import json
from pathlib import Path

from wizard.models.dependency_result import Dependency, DependencyGroup, ManifestIssue
from wizard.parsers.base_parser import BaseParser
from wizard.utils.file_utils import safe_read_file


class NodeParser(BaseParser):
    """Parser for Node.js dependency manifests."""

    @property
    def ecosystem(self) -> str:
        return "Node.js"

    @property
    def supported_files(self) -> list[str]:
        return ["package.json"]

    def parse(self, file_path: Path) -> list[Dependency]:
        """Parse package.json for dependencies."""
        content = safe_read_file(file_path)
        if not content:
            return []

        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return []

        deps: list[Dependency] = []
        rel_path = file_path.name

        # Map section → DependencyGroup
        section_map = {
            "dependencies": DependencyGroup.PRODUCTION,
            "devDependencies": DependencyGroup.DEVELOPMENT,
            "peerDependencies": DependencyGroup.PEER,
            "optionalDependencies": DependencyGroup.OPTIONAL,
        }

        for section, group in section_map.items():
            section_data = data.get(section, {})
            if isinstance(section_data, dict):
                for pkg_name, version_spec in section_data.items():
                    deps.append(Dependency(
                        name=pkg_name,
                        version_constraint=version_spec if isinstance(version_spec, str) else "*",
                        group=group,
                        source_file=rel_path,
                    ))

        return deps

    def validate(self, file_path: Path) -> list[ManifestIssue]:
        """Validate package.json for common issues."""
        issues = super().validate(file_path)

        content = safe_read_file(file_path)
        if not content:
            return issues

        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            issues.append(ManifestIssue(
                file=file_path.name,
                issue_type="malformed",
                message=f"Invalid JSON: {e}",
                severity="error",
            ))
            return issues

        if not isinstance(data, dict):
            issues.append(ManifestIssue(
                file=file_path.name,
                issue_type="malformed",
                message="package.json root must be a JSON object.",
                severity="error",
            ))
            return issues

        # Check for missing name
        if "name" not in data:
            issues.append(ManifestIssue(
                file=file_path.name,
                issue_type="malformed",
                message="Missing 'name' field in package.json.",
                severity="info",
            ))

        # Check for missing version
        if "version" not in data:
            issues.append(ManifestIssue(
                file=file_path.name,
                issue_type="malformed",
                message="Missing 'version' field in package.json.",
                severity="info",
            ))

        # Check for duplicate dependencies across sections
        all_deps: dict[str, list[str]] = {}
        for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
            section_data = data.get(section, {})
            if isinstance(section_data, dict):
                for pkg_name in section_data:
                    all_deps.setdefault(pkg_name, []).append(section)

        for pkg_name, sections in all_deps.items():
            if len(sections) > 1:
                issues.append(ManifestIssue(
                    file=file_path.name,
                    issue_type="duplicate",
                    message=f"'{pkg_name}' appears in multiple sections: {', '.join(sections)}.",
                    severity="warning",
                ))

        return issues
