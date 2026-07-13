"""File system utilities for safe, read-only operations.

All functions in this module are strictly read-only and will never
modify, create, or delete any files or directories.
"""

from __future__ import annotations

import os
from pathlib import Path

from wizard.utils.constants import IGNORE_DIRS


def validate_project_path(path: str) -> Path:
    """Validate that the given path is an existing, readable directory.

    Args:
        path: The path string to validate.

    Returns:
        Resolved Path object.

    Raises:
        FileNotFoundError: If path does not exist.
        NotADirectoryError: If path is not a directory.
        PermissionError: If path is not readable.
    """
    resolved = Path(path).resolve()

    if not resolved.exists():
        raise FileNotFoundError(f"Path does not exist: {resolved}")
    if not resolved.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {resolved}")
    if not os.access(resolved, os.R_OK):
        raise PermissionError(f"Permission denied: {resolved}")

    return resolved


def safe_read_file(path: Path, encoding: str = "utf-8") -> str | None:
    """Safely read a file's contents, returning None on failure.

    Args:
        path: Path to the file.
        encoding: File encoding (default utf-8).

    Returns:
        File contents as string, or None if unreadable.
    """
    try:
        return path.read_text(encoding=encoding)
    except (OSError, UnicodeDecodeError):
        # Try with latin-1 as fallback for binary-adjacent files
        try:
            return path.read_text(encoding="latin-1")
        except (OSError, UnicodeDecodeError):
            return None


def safe_read_bytes(path: Path) -> bytes | None:
    """Safely read a file's raw bytes, returning None on failure."""
    try:
        return path.read_bytes()
    except OSError:
        return None


def walk_project(
    root: Path,
    ignore_dirs: set[str] | None = None,
    max_depth: int | None = None,
) -> list[Path]:
    """Walk a project directory tree, yielding file paths.

    Respects the ignore directory list and optional depth limit.

    Args:
        root: Root directory to walk.
        ignore_dirs: Directory names to skip. Defaults to IGNORE_DIRS.
        max_depth: Maximum directory depth to traverse. None = unlimited.

    Returns:
        List of Path objects for all discovered files.
    """
    if ignore_dirs is None:
        ignore_dirs = IGNORE_DIRS

    files: list[Path] = []
    _walk_recursive(root, root, ignore_dirs, max_depth, files)
    return files


def _walk_recursive(
    current: Path,
    root: Path,
    ignore_dirs: set[str],
    max_depth: int | None,
    accumulator: list[Path],
) -> None:
    """Recursive helper for walk_project."""
    if max_depth is not None:
        depth = len(current.relative_to(root).parts)
        if depth > max_depth:
            return

    try:
        entries = sorted(current.iterdir())
    except PermissionError:
        return

    for entry in entries:
        if entry.is_dir():
            if entry.name not in ignore_dirs and not entry.name.endswith(".egg-info"):
                _walk_recursive(entry, root, ignore_dirs, max_depth, accumulator)
        elif entry.is_file():
            accumulator.append(entry)


def walk_directories(
    root: Path,
    ignore_dirs: set[str] | None = None,
) -> list[Path]:
    """Walk and return all directories (excluding ignored ones).

    Args:
        root: Root directory.
        ignore_dirs: Directory names to skip.

    Returns:
        List of directory Paths.
    """
    if ignore_dirs is None:
        ignore_dirs = IGNORE_DIRS

    dirs: list[Path] = []
    _walk_dirs_recursive(root, ignore_dirs, dirs)
    return dirs


def _walk_dirs_recursive(
    current: Path,
    ignore_dirs: set[str],
    accumulator: list[Path],
) -> None:
    """Recursive helper for walk_directories."""
    try:
        entries = sorted(current.iterdir())
    except PermissionError:
        return

    for entry in entries:
        if entry.is_dir() and entry.name not in ignore_dirs and not entry.name.endswith(".egg-info"):
            accumulator.append(entry)
            _walk_dirs_recursive(entry, ignore_dirs, accumulator)


def get_file_size(path: Path) -> int:
    """Safely get file size in bytes, returning 0 on error."""
    try:
        return path.stat().st_size
    except OSError:
        return 0


def get_relative_path(path: Path, root: Path) -> str:
    """Get a display-friendly relative path."""
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def find_files_by_name(root: Path, filenames: list[str]) -> list[Path]:
    """Find specific files by name within the project root (shallow + recursive).

    Args:
        root: Project root directory.
        filenames: List of filenames to search for.

    Returns:
        List of matching file Paths.
    """
    found: list[Path] = []
    name_set = set(filenames)

    # Check root level first
    for name in filenames:
        candidate = root / name
        if candidate.is_file():
            found.append(candidate)

    # Check one level of subdirectories for nested config
    try:
        for entry in root.iterdir():
            if entry.is_dir() and entry.name not in IGNORE_DIRS:
                for name in name_set:
                    candidate = entry / name
                    if candidate.is_file():
                        found.append(candidate)
    except PermissionError:
        pass

    return found


def format_file_size(size_bytes: int) -> str:
    """Format a file size into a human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1_048_576:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1_073_741_824:
        return f"{size_bytes / 1_048_576:.1f} MB"
    else:
        return f"{size_bytes / 1_073_741_824:.2f} GB"
