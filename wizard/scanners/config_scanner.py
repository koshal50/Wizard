"""Configuration file detection scanner.

Identifies and categorizes known configuration files in the project.
"""

from __future__ import annotations

from pathlib import Path

from wizard.models.analysis_result import ConfigFileInfo
from wizard.utils.constants import CI_CD_DIRS, CONFIG_FILES
from wizard.utils.file_utils import get_relative_path


def scan(project_path: Path) -> list[ConfigFileInfo]:
    """Detect known configuration files in the project.

    Args:
        project_path: Resolved path to the project root.

    Returns:
        List of ConfigFileInfo for detected config files.
    """
    detected: list[ConfigFileInfo] = []

    # Check for known config files at project root
    for filename, category in CONFIG_FILES.items():
        candidate = project_path / filename
        if candidate.is_file():
            detected.append(
                ConfigFileInfo(
                    name=filename,
                    path=get_relative_path(candidate, project_path),
                    category=category,
                )
            )

    # Check for CI/CD directories and their workflow files
    for dir_path, ci_name in CI_CD_DIRS.items():
        ci_dir = project_path / dir_path
        if ci_dir.is_dir():
            try:
                workflow_files = list(ci_dir.iterdir())
                for wf in workflow_files:
                    if wf.is_file() and wf.suffix in (".yml", ".yaml"):
                        detected.append(
                            ConfigFileInfo(
                                name=wf.name,
                                path=get_relative_path(wf, project_path),
                                category=f"CI/CD ({ci_name})",
                            )
                        )
            except PermissionError:
                pass

    # Check for requirements subdirectory
    req_dir = project_path / "requirements"
    if req_dir.is_dir():
        try:
            for req_file in req_dir.iterdir():
                if req_file.is_file() and req_file.suffix == ".txt":
                    detected.append(
                        ConfigFileInfo(
                            name=req_file.name,
                            path=get_relative_path(req_file, project_path),
                            category="Python Dependencies",
                        )
                    )
        except PermissionError:
            pass

    # Sort by category then name for consistent output
    detected.sort(key=lambda c: (c.category, c.name))

    return detected
