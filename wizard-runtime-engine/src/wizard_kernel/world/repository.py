"""Repository path validation — resolves and guards the workspace before any sandbox is started.

Called by the loop before sandbox.start() so that path problems surface
as a clean ValueError (→ LifecycleState.failed), not a cryptic OS error
buried inside a sandbox call.
"""
from pathlib import Path


def validate(raw_path: str) -> Path:
    """Resolve, check existence and type of a repository path.

    Returns the resolved absolute Path on success.
    Raises ValueError with a clear message on any problem.

    This is the only place that touches the filesystem for path validation —
    the sandbox owns all subsequent access.
    """
    p = Path(raw_path).resolve()

    if not p.exists():
        raise ValueError(
            f"repository path does not exist: {raw_path!r} "
            f"(resolved to {p})"
        )
    if not p.is_dir():
        raise ValueError(
            f"repository path is not a directory: {raw_path!r} "
            f"(resolved to {p})"
        )
    return p
