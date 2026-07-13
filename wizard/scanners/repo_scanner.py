"""Repository information scanner.

Detects project name, root directory, repository type, Git status,
and hidden project metadata.
"""

from __future__ import annotations

from pathlib import Path

from wizard.models.analysis_result import RepoInfo
from wizard.utils.file_utils import safe_read_file
from wizard.utils.git_utils import get_git_info, is_git_repo


def scan(project_path: Path) -> RepoInfo:
    """Scan for basic repository information.

    Args:
        project_path: Resolved path to the project root.

    Returns:
        RepoInfo with detected repository details.
    """
    project_name = _detect_project_name(project_path)
    git_initialized = is_git_repo(project_path)
    metadata = _extract_metadata(project_path)

    info = RepoInfo(
        project_name=project_name,
        root_directory=str(project_path),
        git_initialized=git_initialized,
        metadata=metadata,
    )

    if git_initialized:
        git_info = get_git_info(project_path)
        info.repo_type = git_info["repo_type"]
        info.git_branch = git_info["branch"]
        info.git_remote_url = git_info["remote_url"]

    return info


def _detect_project_name(project_path: Path) -> str:
    """Detect the project name from metadata files or directory name.

    Priority:
    1. pyproject.toml [project.name]
    2. package.json "name"
    3. Cargo.toml [package.name]
    4. setup.cfg [metadata.name]
    5. Directory name
    """
    # Try pyproject.toml
    name = _name_from_pyproject(project_path / "pyproject.toml")
    if name:
        return name

    # Try package.json
    name = _name_from_package_json(project_path / "package.json")
    if name:
        return name

    # Try Cargo.toml
    name = _name_from_cargo_toml(project_path / "Cargo.toml")
    if name:
        return name

    # Try setup.cfg
    name = _name_from_setup_cfg(project_path / "setup.cfg")
    if name:
        return name

    # Fallback: directory name
    return project_path.name


def _name_from_pyproject(path: Path) -> str | None:
    """Extract project name from pyproject.toml."""
    if not path.is_file():
        return None

    content = safe_read_file(path)
    if not content:
        return None

    try:
        import sys
        if sys.version_info >= (3, 11):
            import tomllib
        else:
            import tomli as tomllib

        data = tomllib.loads(content)
        return data.get("project", {}).get("name") or data.get("tool", {}).get("poetry", {}).get("name")
    except Exception:
        return None


def _name_from_package_json(path: Path) -> str | None:
    """Extract project name from package.json."""
    if not path.is_file():
        return None

    content = safe_read_file(path)
    if not content:
        return None

    try:
        import json
        data = json.loads(content)
        return data.get("name")
    except (json.JSONDecodeError, KeyError):
        return None


def _name_from_cargo_toml(path: Path) -> str | None:
    """Extract project name from Cargo.toml."""
    if not path.is_file():
        return None

    content = safe_read_file(path)
    if not content:
        return None

    try:
        import sys
        if sys.version_info >= (3, 11):
            import tomllib
        else:
            import tomli as tomllib

        data = tomllib.loads(content)
        return data.get("package", {}).get("name")
    except Exception:
        return None


def _name_from_setup_cfg(path: Path) -> str | None:
    """Extract project name from setup.cfg."""
    if not path.is_file():
        return None

    try:
        import configparser
        parser = configparser.ConfigParser()
        parser.read(str(path), encoding="utf-8")
        return parser.get("metadata", "name", fallback=None)
    except (configparser.Error, OSError):
        return None


def _extract_metadata(project_path: Path) -> dict[str, str]:
    """Extract additional project metadata from config files."""
    metadata: dict[str, str] = {}

    # Description from pyproject.toml
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
                desc = (
                    data.get("project", {}).get("description")
                    or data.get("tool", {}).get("poetry", {}).get("description")
                )
                if desc:
                    metadata["description"] = desc

                version = (
                    data.get("project", {}).get("version")
                    or data.get("tool", {}).get("poetry", {}).get("version")
                )
                if version:
                    metadata["version"] = version
            except Exception:
                pass

    # Description from package.json
    pkg_json = project_path / "package.json"
    if pkg_json.is_file() and "description" not in metadata:
        content = safe_read_file(pkg_json)
        if content:
            try:
                import json
                data = json.loads(content)
                if data.get("description"):
                    metadata["description"] = data["description"]
                if data.get("version"):
                    metadata["version"] = data["version"]
            except (json.JSONDecodeError, KeyError):
                pass

    return metadata
