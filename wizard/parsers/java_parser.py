"""Java dependency manifest parser.

Handles: pom.xml (Maven), build.gradle / build.gradle.kts (Gradle)
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from wizard.models.dependency_result import Dependency, DependencyGroup, ManifestIssue
from wizard.parsers.base_parser import BaseParser
from wizard.utils.file_utils import safe_read_file


class JavaParser(BaseParser):
    """Parser for Java dependency manifests."""

    @property
    def ecosystem(self) -> str:
        return "Java"

    @property
    def supported_files(self) -> list[str]:
        return ["pom.xml", "build.gradle", "build.gradle.kts"]

    def parse(self, file_path: Path) -> list[Dependency]:
        """Route to appropriate parser based on filename."""
        name = file_path.name
        try:
            if name == "pom.xml":
                return self._parse_pom_xml(file_path)
            elif name in ("build.gradle", "build.gradle.kts"):
                return self._parse_build_gradle(file_path)
        except Exception:
            return []
        return []

    def validate(self, file_path: Path) -> list[ManifestIssue]:
        """Validate Java manifest files."""
        issues = super().validate(file_path)

        if file_path.name == "pom.xml":
            content = safe_read_file(file_path)
            if content:
                try:
                    ET.fromstring(content)
                except ET.ParseError as e:
                    issues.append(ManifestIssue(
                        file=file_path.name,
                        issue_type="malformed",
                        message=f"Invalid XML: {e}",
                        severity="error",
                    ))

        return issues

    # -----------------------------------------------------------------------
    # pom.xml (Maven)
    # -----------------------------------------------------------------------

    def _parse_pom_xml(self, file_path: Path) -> list[Dependency]:
        """Parse Maven pom.xml for dependencies."""
        content = safe_read_file(file_path)
        if not content:
            return []

        try:
            root = ET.fromstring(content)
        except ET.ParseError:
            return []

        deps: list[Dependency] = []
        rel_path = file_path.name

        # Maven namespace handling
        ns = ""
        match = re.match(r'\{(.+?)\}', root.tag)
        if match:
            ns = match.group(1)

        def tag(name: str) -> str:
            return f"{{{ns}}}{name}" if ns else name

        # Find all <dependency> elements
        for dep_elem in root.iter(tag("dependency")):
            group_id = dep_elem.findtext(tag("groupId"), "").strip()
            artifact_id = dep_elem.findtext(tag("artifactId"), "").strip()
            version = dep_elem.findtext(tag("version"), "").strip()
            scope = dep_elem.findtext(tag("scope"), "compile").strip().lower()

            if not artifact_id:
                continue

            # Map Maven scopes to DependencyGroup
            group = self._maven_scope_to_group(scope)

            # Use groupId:artifactId as the full name
            full_name = f"{group_id}:{artifact_id}" if group_id else artifact_id

            deps.append(Dependency(
                name=full_name,
                version_constraint=version or "${version}",
                group=group,
                source_file=rel_path,
            ))

        return deps

    def _maven_scope_to_group(self, scope: str) -> DependencyGroup:
        """Map Maven scope to DependencyGroup."""
        scope_map = {
            "compile": DependencyGroup.PRODUCTION,
            "runtime": DependencyGroup.PRODUCTION,
            "provided": DependencyGroup.PRODUCTION,
            "test": DependencyGroup.TESTING,
            "system": DependencyGroup.PRODUCTION,
            "import": DependencyGroup.PRODUCTION,
        }
        return scope_map.get(scope, DependencyGroup.PRODUCTION)

    # -----------------------------------------------------------------------
    # build.gradle / build.gradle.kts
    # -----------------------------------------------------------------------

    def _parse_build_gradle(self, file_path: Path) -> list[Dependency]:
        """Parse Gradle build file for dependencies (regex-based)."""
        content = safe_read_file(file_path)
        if not content:
            return []

        deps: list[Dependency] = []
        rel_path = file_path.name

        # Match patterns like:
        #   implementation 'group:artifact:version'
        #   implementation "group:artifact:version"
        #   testImplementation("group:artifact:version")
        #   api 'group:artifact:version'
        patterns = [
            # Groovy style: configuration 'group:artifact:version'
            r'(\w+)\s+[\'"]([^:\'"]+):([^:\'"]+):?([^\'"]*)[\'"]',
            # Kotlin DSL: configuration("group:artifact:version")
            r'(\w+)\s*\(\s*[\'"]([^:\'"]+):([^:\'"]+):?([^\'"]*)[\'"]',
        ]

        gradle_configs = {
            "implementation": DependencyGroup.PRODUCTION,
            "api": DependencyGroup.PRODUCTION,
            "compileOnly": DependencyGroup.PRODUCTION,
            "runtimeOnly": DependencyGroup.PRODUCTION,
            "testImplementation": DependencyGroup.TESTING,
            "testCompileOnly": DependencyGroup.TESTING,
            "testRuntimeOnly": DependencyGroup.TESTING,
            "androidTestImplementation": DependencyGroup.TESTING,
            "kapt": DependencyGroup.BUILD,
            "annotationProcessor": DependencyGroup.BUILD,
        }

        for pattern in patterns:
            for match in re.finditer(pattern, content):
                config = match.group(1)
                group_id = match.group(2)
                artifact_id = match.group(3)
                version = match.group(4) if match.group(4) else ""

                dep_group = gradle_configs.get(config, DependencyGroup.PRODUCTION)
                full_name = f"{group_id}:{artifact_id}"

                deps.append(Dependency(
                    name=full_name,
                    version_constraint=version or "*",
                    group=dep_group,
                    source_file=rel_path,
                ))

        return deps
