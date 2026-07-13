"""Configuration file support for Wizard.

Loads settings from .wizardrc files (YAML format).

Search order:
1. Project directory .wizardrc
2. User home directory .wizardrc
3. Defaults
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from wizard.utils.file_utils import safe_read_file


# Default configuration values
DEFAULTS: dict[str, Any] = {
    "show_banner": True,
    "default_format": "rich",  # "rich" | "json"
    "summary_mode": False,
    "verbose": False,
    "ignore_dirs": [],
}


def load_config(project_path: str = ".") -> dict[str, Any]:
    """Load configuration from .wizardrc files.

    Merges project-level config over user-level config over defaults.

    Args:
        project_path: Path to the project directory.

    Returns:
        Merged configuration dictionary.
    """
    config = dict(DEFAULTS)

    # Load user-level config (~/.wizardrc)
    user_rc = Path.home() / ".wizardrc"
    user_config = _load_rc_file(user_rc)
    if user_config:
        config.update(user_config)

    # Load project-level config (.wizardrc in project dir)
    project_rc = Path(project_path).resolve() / ".wizardrc"
    project_config = _load_rc_file(project_rc)
    if project_config:
        config.update(project_config)

    return config


def _load_rc_file(path: Path) -> dict[str, Any] | None:
    """Load and parse a .wizardrc YAML file.

    Args:
        path: Path to the .wizardrc file.

    Returns:
        Parsed configuration dict, or None if file doesn't exist or is invalid.
    """
    if not path.is_file():
        return None

    content = safe_read_file(path)
    if not content:
        return None

    try:
        import yaml
        data = yaml.safe_load(content)
        if isinstance(data, dict):
            return data
        return None
    except Exception:
        return None
