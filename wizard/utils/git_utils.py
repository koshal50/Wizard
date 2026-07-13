"""Git repository detection and information extraction.

Read-only: only reads .git directory contents, never runs git commands.
"""

from __future__ import annotations

import configparser
from pathlib import Path


def is_git_repo(project_path: Path) -> bool:
    """Check if the project has a .git directory."""
    return (project_path / ".git").is_dir()


def get_git_info(project_path: Path) -> dict[str, str | None]:
    """Extract basic Git information from the .git directory.

    Reads .git/HEAD and .git/config without executing git commands.

    Returns:
        Dictionary with keys: branch, remote_url, repo_type.
    """
    git_dir = project_path / ".git"
    info: dict[str, str | None] = {
        "branch": None,
        "remote_url": None,
        "repo_type": "git",
    }

    if not git_dir.is_dir():
        return info

    # Read current branch from HEAD
    head_file = git_dir / "HEAD"
    if head_file.is_file():
        try:
            head_content = head_file.read_text(encoding="utf-8").strip()
            if head_content.startswith("ref: refs/heads/"):
                info["branch"] = head_content.replace("ref: refs/heads/", "")
            elif len(head_content) == 40:
                info["branch"] = f"detached ({head_content[:8]})"
        except (OSError, UnicodeDecodeError):
            pass

    # Read remote URL from config
    config_file = git_dir / "config"
    if config_file.is_file():
        try:
            parser = configparser.ConfigParser()
            parser.read(str(config_file), encoding="utf-8")

            # Look for [remote "origin"]
            for section in parser.sections():
                if section.startswith('remote "') and section.endswith('"'):
                    remote_name = section[8:-1]
                    if remote_name == "origin":
                        info["remote_url"] = parser.get(section, "url", fallback=None)
                        break
        except (configparser.Error, OSError, UnicodeDecodeError):
            pass

    return info
