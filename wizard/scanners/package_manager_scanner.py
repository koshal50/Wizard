"""Package manager detection scanner.

Identifies package managers by detecting manifest and lock files.
"""

from __future__ import annotations

from pathlib import Path

from wizard.models.analysis_result import PackageManagerInfo
from wizard.utils.constants import PACKAGE_MANAGER_INDICATORS
from wizard.utils.file_utils import safe_read_file


def scan(project_path: Path) -> list[PackageManagerInfo]:
    """Detect package managers in use.

    Args:
        project_path: Resolved path to the project root.

    Returns:
        List of detected PackageManagerInfo.
    """
    detected: list[PackageManagerInfo] = []

    for pm_name, indicators in PACKAGE_MANAGER_INDICATORS.items():
        manifest_files = _check_package_manager(project_path, pm_name, indicators)
        if manifest_files:
            detected.append(
                PackageManagerInfo(
                    name=pm_name,
                    ecosystem=indicators.get("ecosystem", "Unknown"),
                    manifest_files=manifest_files,
                )
            )

    # Special handling: if package.json exists but no lock file detected,
    # assume npm as default
    if not any(pm.ecosystem == "Node.js" for pm in detected):
        if (project_path / "package.json").is_file():
            detected.append(
                PackageManagerInfo(
                    name="npm",
                    ecosystem="Node.js",
                    manifest_files=["package.json"],
                )
            )

    return detected


def _check_package_manager(
    project_path: Path,
    pm_name: str,
    indicators: dict,
) -> list[str]:
    """Check for a specific package manager's presence.

    Returns:
        List of found manifest file paths (relative), empty if not detected.
    """
    found_files: list[str] = []

    # Check direct file indicators
    for filename in indicators.get("files", []):
        candidate = project_path / filename
        if candidate.is_file():
            found_files.append(filename)

    # Check directory patterns (e.g., requirements/*.txt)
    for pattern in indicators.get("dir_patterns", []):
        matches = list(project_path.glob(pattern))
        for match in matches:
            try:
                rel_path = str(match.relative_to(project_path))
                found_files.append(rel_path)
            except ValueError:
                found_files.append(str(match))

    # Check TOML sections (e.g., [tool.poetry] in pyproject.toml)
    for section_path in indicators.get("toml_sections", []):
        if _check_toml_section(project_path / "pyproject.toml", section_path):
            if "pyproject.toml" not in found_files:
                found_files.append("pyproject.toml")

    return found_files


def _check_toml_section(toml_path: Path, section_path: str) -> bool:
    """Check if a TOML file contains a specific nested section.

    Args:
        toml_path: Path to the TOML file.
        section_path: Dot-separated section path (e.g., "tool.poetry").
    """
    if not toml_path.is_file():
        return False

    content = safe_read_file(toml_path)
    if not content:
        return False

    try:
        import sys
        if sys.version_info >= (3, 11):
            import tomllib
        else:
            import tomli as tomllib

        data = tomllib.loads(content)
        parts = section_path.split(".")
        current = data
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return False
        return True
    except Exception:
        return False
