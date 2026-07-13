"""Rust dependency manifest parser.

Handles: Cargo.toml
"""

from __future__ import annotations

from pathlib import Path

from wizard.models.dependency_result import Dependency, DependencyGroup, ManifestIssue
from wizard.parsers.base_parser import BaseParser
from wizard.utils.file_utils import safe_read_file


class RustParser(BaseParser):
    """Parser for Rust Cargo.toml dependency manifests."""

    @property
    def ecosystem(self) -> str:
        return "Rust"

    @property
    def supported_files(self) -> list[str]:
        return ["Cargo.toml"]

    def parse(self, file_path: Path) -> list[Dependency]:
        """Parse Cargo.toml for dependencies."""
        content = safe_read_file(file_path)
        if not content:
            return []

        try:
            import sys
            if sys.version_info >= (3, 11):
                import tomllib
            else:
                import tomli as tomllib

            data = tomllib.loads(content)
        except Exception:
            return []

        deps: list[Dependency] = []
        rel_path = file_path.name

        # [dependencies]
        for name, spec in data.get("dependencies", {}).items():
            dep = self._parse_cargo_dependency(name, spec, DependencyGroup.PRODUCTION, rel_path)
            deps.append(dep)

        # [dev-dependencies]
        for name, spec in data.get("dev-dependencies", {}).items():
            dep = self._parse_cargo_dependency(name, spec, DependencyGroup.DEVELOPMENT, rel_path)
            deps.append(dep)

        # [build-dependencies]
        for name, spec in data.get("build-dependencies", {}).items():
            dep = self._parse_cargo_dependency(name, spec, DependencyGroup.BUILD, rel_path)
            deps.append(dep)

        return deps

    def _parse_cargo_dependency(
        self,
        name: str,
        spec: str | dict,
        group: DependencyGroup,
        source_file: str,
    ) -> Dependency:
        """Parse a single Cargo dependency specification.

        Cargo dependencies can be:
          - A version string: "1.0"
          - A table: { version = "1.0", features = [...], optional = true }
        """
        extras: list[str] = []

        if isinstance(spec, str):
            version_constraint = spec
        elif isinstance(spec, dict):
            version_constraint = spec.get("version", "*")
            features = spec.get("features", [])
            extras = features if isinstance(features, list) else []

            if spec.get("optional", False):
                group = DependencyGroup.OPTIONAL
        else:
            version_constraint = "*"

        return Dependency(
            name=name,
            version_constraint=version_constraint,
            group=group,
            source_file=source_file,
            extras=extras,
        )

    def validate(self, file_path: Path) -> list[ManifestIssue]:
        """Validate Cargo.toml."""
        issues = super().validate(file_path)

        content = safe_read_file(file_path)
        if not content:
            return issues

        try:
            import sys
            if sys.version_info >= (3, 11):
                import tomllib
            else:
                import tomli as tomllib

            data = tomllib.loads(content)

            # Check for missing [package] section
            if "package" not in data and "workspace" not in data:
                issues.append(ManifestIssue(
                    file=file_path.name,
                    issue_type="malformed",
                    message="Cargo.toml is missing [package] section.",
                    severity="warning",
                ))

        except Exception as e:
            issues.append(ManifestIssue(
                file=file_path.name,
                issue_type="malformed",
                message=f"Invalid TOML syntax: {e}",
                severity="error",
            ))

        return issues
