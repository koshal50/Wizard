"""Python dependency manifest parser.

Handles: requirements.txt, pyproject.toml (PEP 621 + Poetry), poetry.lock
"""

from __future__ import annotations

import re
from pathlib import Path

from wizard.models.dependency_result import Dependency, DependencyGroup, ManifestIssue
from wizard.parsers.base_parser import BaseParser
from wizard.utils.file_utils import safe_read_file


class PythonParser(BaseParser):
    """Parser for Python dependency manifests."""

    @property
    def ecosystem(self) -> str:
        return "Python"

    @property
    def supported_files(self) -> list[str]:
        return ["requirements.txt", "pyproject.toml", "poetry.lock", "Pipfile"]

    def parse(self, file_path: Path) -> list[Dependency]:
        """Route to the appropriate parser based on filename."""
        name = file_path.name
        try:
            if name == "requirements.txt" or name.endswith(".txt"):
                return self._parse_requirements_txt(file_path)
            elif name == "pyproject.toml":
                return self._parse_pyproject_toml(file_path)
            elif name == "poetry.lock":
                return self._parse_poetry_lock(file_path)
            elif name == "Pipfile":
                return self._parse_pipfile(file_path)
        except Exception:
            return []
        return []

    def validate(self, file_path: Path) -> list[ManifestIssue]:
        """Validate Python manifest files."""
        issues = super().validate(file_path)

        content = safe_read_file(file_path)
        if not content:
            return issues

        name = file_path.name

        if name == "requirements.txt" or (name.endswith(".txt") and "requirements" in str(file_path)):
            issues.extend(self._validate_requirements_txt(file_path, content))
        elif name == "pyproject.toml":
            issues.extend(self._validate_pyproject_toml(file_path, content))

        return issues

    # -----------------------------------------------------------------------
    # requirements.txt
    # -----------------------------------------------------------------------

    def _parse_requirements_txt(self, file_path: Path) -> list[Dependency]:
        """Parse a requirements.txt file."""
        content = safe_read_file(file_path)
        if not content:
            return []

        deps: list[Dependency] = []
        rel_path = file_path.name

        for line in content.splitlines():
            line = line.strip()

            # Skip blanks, comments, options
            if not line or line.startswith("#") or line.startswith("-"):
                continue

            # Handle environment markers (e.g., "package; python_version >= '3.8'")
            line = line.split(";")[0].strip()

            # Parse package name and version
            dep = self._parse_requirement_line(line, rel_path)
            if dep:
                deps.append(dep)

        return deps

    def _parse_requirement_line(self, line: str, source_file: str) -> Dependency | None:
        """Parse a single requirement line."""
        # Match: package[extras]>=version,<version
        match = re.match(
            r'^([a-zA-Z0-9_][\w.\-]*)\s*(?:\[([^\]]+)\])?\s*(.*)',
            line,
        )
        if not match:
            return None

        name = match.group(1).strip()
        extras_str = match.group(2)
        version_part = match.group(3).strip()

        extras = [e.strip() for e in extras_str.split(",")] if extras_str else []
        version_constraint = version_part if version_part else "*"

        return Dependency(
            name=name,
            version_constraint=version_constraint,
            group=DependencyGroup.PRODUCTION,
            source_file=source_file,
            extras=extras,
        )

    def _validate_requirements_txt(self, file_path: Path, content: str) -> list[ManifestIssue]:
        """Validate requirements.txt for common issues."""
        issues: list[ManifestIssue] = []
        seen_packages: dict[str, int] = {}

        for line_num, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("-"):
                continue

            # Check for package name
            match = re.match(r'^([a-zA-Z0-9_][\w.\-]*)', stripped)
            if match:
                pkg_name = match.group(1).lower()
                if pkg_name in seen_packages:
                    issues.append(ManifestIssue(
                        file=file_path.name,
                        issue_type="duplicate",
                        message=f"Duplicate package '{match.group(1)}' (first seen at line {seen_packages[pkg_name]}).",
                        severity="warning",
                        line_number=line_num,
                    ))
                else:
                    seen_packages[pkg_name] = line_num
            else:
                # Malformed line
                if not stripped.startswith("http") and "://" not in stripped:
                    issues.append(ManifestIssue(
                        file=file_path.name,
                        issue_type="malformed",
                        message=f"Unrecognized entry at line {line_num}: '{stripped[:60]}'",
                        severity="info",
                        line_number=line_num,
                    ))

        return issues

    # -----------------------------------------------------------------------
    # pyproject.toml
    # -----------------------------------------------------------------------

    def _parse_pyproject_toml(self, file_path: Path) -> list[Dependency]:
        """Parse pyproject.toml for dependencies."""
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

        # PEP 621: [project.dependencies]
        for dep_str in data.get("project", {}).get("dependencies", []):
            dep = self._parse_pep621_dependency(dep_str, DependencyGroup.PRODUCTION, rel_path)
            if dep:
                deps.append(dep)

        # PEP 621: [project.optional-dependencies]
        optional = data.get("project", {}).get("optional-dependencies", {})
        for group_name, dep_list in optional.items():
            group = self._classify_optional_group(group_name)
            for dep_str in dep_list:
                dep = self._parse_pep621_dependency(dep_str, group, rel_path)
                if dep:
                    deps.append(dep)

        # Poetry: [tool.poetry.dependencies]
        poetry_deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
        for pkg_name, version_spec in poetry_deps.items():
            if pkg_name.lower() == "python":
                continue
            dep = self._parse_poetry_dependency(pkg_name, version_spec, DependencyGroup.PRODUCTION, rel_path)
            deps.append(dep)

        # Poetry: [tool.poetry.dev-dependencies] or [tool.poetry.group.dev.dependencies]
        dev_deps = data.get("tool", {}).get("poetry", {}).get("dev-dependencies", {})
        for pkg_name, version_spec in dev_deps.items():
            dep = self._parse_poetry_dependency(pkg_name, version_spec, DependencyGroup.DEVELOPMENT, rel_path)
            deps.append(dep)

        # Poetry groups (tool.poetry.group.<name>.dependencies)
        groups = data.get("tool", {}).get("poetry", {}).get("group", {})
        for group_name, group_data in groups.items():
            group = self._classify_optional_group(group_name)
            group_deps = group_data.get("dependencies", {})
            for pkg_name, version_spec in group_deps.items():
                dep = self._parse_poetry_dependency(pkg_name, version_spec, group, rel_path)
                deps.append(dep)

        return deps

    def _parse_pep621_dependency(
        self, dep_str: str, group: DependencyGroup, source_file: str
    ) -> Dependency | None:
        """Parse a PEP 621 dependency string like 'package>=1.0,<2.0'."""
        dep_str = dep_str.split(";")[0].strip()  # Remove markers
        match = re.match(r'^([a-zA-Z0-9_][\w.\-]*)\s*(?:\[([^\]]+)\])?\s*(.*)', dep_str)
        if not match:
            return None

        name = match.group(1).strip()
        extras_str = match.group(2)
        version_part = match.group(3).strip()

        extras = [e.strip() for e in extras_str.split(",")] if extras_str else []
        version_constraint = version_part if version_part else "*"

        return Dependency(
            name=name,
            version_constraint=version_constraint,
            group=group,
            source_file=source_file,
            extras=extras,
        )

    def _parse_poetry_dependency(
        self, name: str, version_spec: str | dict, group: DependencyGroup, source_file: str
    ) -> Dependency:
        """Parse a Poetry dependency entry."""
        if isinstance(version_spec, str):
            version_constraint = version_spec
            extras = []
        elif isinstance(version_spec, dict):
            version_constraint = version_spec.get("version", "*")
            extras = version_spec.get("extras", [])
            if version_spec.get("optional", False):
                group = DependencyGroup.OPTIONAL
        else:
            version_constraint = "*"
            extras = []

        return Dependency(
            name=name,
            version_constraint=version_constraint,
            group=group,
            source_file=source_file,
            extras=extras if isinstance(extras, list) else [],
        )

    def _classify_optional_group(self, group_name: str) -> DependencyGroup:
        """Map an optional dependency group name to a DependencyGroup."""
        name_lower = group_name.lower()
        if name_lower in ("dev", "develop", "development"):
            return DependencyGroup.DEVELOPMENT
        elif name_lower in ("test", "tests", "testing"):
            return DependencyGroup.TESTING
        elif name_lower in ("build", "ci"):
            return DependencyGroup.BUILD
        elif name_lower in ("optional", "extras"):
            return DependencyGroup.OPTIONAL
        else:
            return DependencyGroup.OPTIONAL

    def _validate_pyproject_toml(self, file_path: Path, content: str) -> list[ManifestIssue]:
        """Validate pyproject.toml."""
        issues: list[ManifestIssue] = []
        try:
            import sys
            if sys.version_info >= (3, 11):
                import tomllib
            else:
                import tomli as tomllib

            tomllib.loads(content)
        except Exception as e:
            issues.append(ManifestIssue(
                file=file_path.name,
                issue_type="malformed",
                message=f"Invalid TOML syntax: {e}",
                severity="error",
            ))

        return issues

    # -----------------------------------------------------------------------
    # poetry.lock (lightweight — just extract direct declarations)
    # -----------------------------------------------------------------------

    def _parse_poetry_lock(self, file_path: Path) -> list[Dependency]:
        """Parse poetry.lock for top-level package declarations."""
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
        for package in data.get("package", []):
            name = package.get("name", "")
            version = package.get("version", "*")
            category = package.get("category", "main")

            if not name:
                continue

            group = DependencyGroup.DEVELOPMENT if category == "dev" else DependencyGroup.PRODUCTION

            deps.append(Dependency(
                name=name,
                version_constraint=f"=={version}" if version != "*" else "*",
                group=group,
                source_file=file_path.name,
            ))

        return deps

    # -----------------------------------------------------------------------
    # Pipfile (lightweight)
    # -----------------------------------------------------------------------

    def _parse_pipfile(self, file_path: Path) -> list[Dependency]:
        """Parse Pipfile for dependency declarations."""
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

        for pkg_name, version_spec in data.get("packages", {}).items():
            version = version_spec if isinstance(version_spec, str) else version_spec.get("version", "*") if isinstance(version_spec, dict) else "*"
            deps.append(Dependency(
                name=pkg_name,
                version_constraint=version,
                group=DependencyGroup.PRODUCTION,
                source_file=file_path.name,
            ))

        for pkg_name, version_spec in data.get("dev-packages", {}).items():
            version = version_spec if isinstance(version_spec, str) else version_spec.get("version", "*") if isinstance(version_spec, dict) else "*"
            deps.append(Dependency(
                name=pkg_name,
                version_constraint=version,
                group=DependencyGroup.DEVELOPMENT,
                source_file=file_path.name,
            ))

        return deps
