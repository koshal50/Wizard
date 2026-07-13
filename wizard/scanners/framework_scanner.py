"""Framework detection scanner.

Detects common frameworks by analyzing configuration files,
dependency manifests, and project structure patterns.
"""

from __future__ import annotations

import json
from pathlib import Path

from wizard.models.analysis_result import FrameworkInfo
from wizard.utils.constants import FRAMEWORK_INDICATORS
from wizard.utils.file_utils import safe_read_file


def scan(project_path: Path) -> list[FrameworkInfo]:
    """Detect frameworks used in the project.

    Args:
        project_path: Resolved path to the project root.

    Returns:
        List of detected FrameworkInfo.
    """
    detected: list[FrameworkInfo] = []
    declared_deps = _collect_declared_dependencies(project_path)

    for framework_name, indicators in FRAMEWORK_INDICATORS.items():
        result = _check_framework(project_path, framework_name, indicators, declared_deps)
        if result:
            detected.append(result)

    return detected


def _check_framework(
    project_path: Path,
    name: str,
    indicators: dict,
    declared_deps: set[str],
) -> FrameworkInfo | None:
    """Check if a specific framework is present.

    Uses a multi-signal approach: files, dependencies, and directory patterns.
    """
    ecosystem = indicators.get("ecosystem", "Unknown")
    signals: list[str] = []

    # Check for indicator files at project root
    for filename in indicators.get("files", []):
        candidate = project_path / filename
        if candidate.is_file():
            signals.append(f"file: {filename}")

    # Check for dependency declarations
    for dep_name in indicators.get("dependencies", []):
        if dep_name.lower() in declared_deps:
            signals.append(f"dependency: {dep_name}")

    # Check directory patterns (shallow search)
    for pattern in indicators.get("dir_patterns", []):
        matches = list(project_path.glob(pattern))
        if matches:
            signals.append(f"pattern: {pattern}")

    if not signals:
        return None

    # Determine confidence based on signal count
    if len(signals) >= 2:
        confidence = "high"
    elif any(s.startswith("dependency:") for s in signals):
        confidence = "high"
    elif any(s.startswith("file:") for s in signals):
        confidence = "medium"
    else:
        confidence = "low"

    return FrameworkInfo(
        name=name,
        ecosystem=ecosystem,
        confidence=confidence,
        detection_source="; ".join(signals),
    )


def _collect_declared_dependencies(project_path: Path) -> set[str]:
    """Collect dependency names from common manifest files.

    This is a lightweight scan — full parsing is done by the parsers module.
    """
    deps: set[str] = set()

    # Python: requirements.txt
    req_txt = project_path / "requirements.txt"
    if req_txt.is_file():
        content = safe_read_file(req_txt)
        if content:
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith("#") and not line.startswith("-"):
                    # Extract package name (before version specifier)
                    pkg = line.split("==")[0].split(">=")[0].split("<=")[0].split("~=")[0].split("!=")[0].split("[")[0].strip()
                    if pkg:
                        deps.add(pkg.lower())

    # Python: pyproject.toml dependencies
    pyproject = project_path / "pyproject.toml"
    if pyproject.is_file():
        content = safe_read_file(pyproject)
        if content:
            try:
                import sys
                if sys.version_info >= (3, 11):
                    import tomllib
                else:
                    import tomli as tomllib

                data = tomllib.loads(content)

                # PEP 621 dependencies
                for dep_str in data.get("project", {}).get("dependencies", []):
                    pkg = dep_str.split("==")[0].split(">=")[0].split("<=")[0].split("~=")[0].split("[")[0].strip()
                    deps.add(pkg.lower())

                # Poetry dependencies
                for dep_name in data.get("tool", {}).get("poetry", {}).get("dependencies", {}):
                    if dep_name.lower() != "python":
                        deps.add(dep_name.lower())

            except Exception:
                pass

    # Node.js: package.json
    pkg_json = project_path / "package.json"
    if pkg_json.is_file():
        content = safe_read_file(pkg_json)
        if content:
            try:
                data = json.loads(content)
                for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
                    for dep_name in data.get(section, {}):
                        deps.add(dep_name.lower())
            except (json.JSONDecodeError, KeyError):
                pass

    # Java: pom.xml (lightweight check for artifact IDs)
    pom_xml = project_path / "pom.xml"
    if pom_xml.is_file():
        content = safe_read_file(pom_xml)
        if content:
            import re
            for match in re.finditer(r"<artifactId>\s*([^<]+)\s*</artifactId>", content):
                deps.add(match.group(1).lower())

    # Rust: Cargo.toml
    cargo_toml = project_path / "Cargo.toml"
    if cargo_toml.is_file():
        content = safe_read_file(cargo_toml)
        if content:
            try:
                import sys
                if sys.version_info >= (3, 11):
                    import tomllib
                else:
                    import tomli as tomllib

                data = tomllib.loads(content)
                for dep_name in data.get("dependencies", {}):
                    deps.add(dep_name.lower())
            except Exception:
                pass

    return deps
