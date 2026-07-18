"""Fast Scanner — produces RepositoryManifest from file tree metadata only.
Never reads file contents. Completes in milliseconds even on large repos."""
import os
from pathlib import Path
from wizard_kernel.contracts.manifest import RepositoryManifest

# Well-known signal files — Planner uses these to identify technologies.
# No technology meaning in the Kernel; just flagged for the Planner.
_SIGNALS: frozenset[str] = frozenset({
    "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "Dockerfile", "dockerfile", "docker-compose.yml", "docker-compose.yaml",
    "requirements.txt", "setup.py", "setup.cfg", "pyproject.toml", "Pipfile", "Pipfile.lock",
    "pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle",
    "Cargo.toml", "Cargo.lock",
    "go.mod", "go.sum",
    "tsconfig.json", "jsconfig.json", "next.config.js", "next.config.ts",
    "vite.config.ts", "vite.config.js", "angular.json", "nuxt.config.ts",
    "Makefile", "CMakeLists.txt", "meson.build",
    "composer.json", "artisan",
    ".env.example", ".env.sample",
    "Gemfile", "Gemfile.lock",
    "mix.exs",
})

_SKIP_DIRS: frozenset[str] = frozenset({
    "node_modules", "__pycache__", ".venv", "venv", ".git",
    "dist", "build", ".next", ".nuxt", "target", ".gradle",
    ".idea", ".vscode", "coverage", ".pytest_cache", ".ruff_cache",
})

_MAX_DEPTH = 4


def scan(repo_path: str, investigation_id: str) -> RepositoryManifest:
    root = Path(repo_path).resolve()
    tree: list[str] = []
    extensions: dict[str, int] = {}
    key_files: list[str] = []
    total_files = total_dirs = size_approx = 0

    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root)
        depth = len(rel_dir.parts)

        if depth >= _MAX_DEPTH:
            dirnames.clear()
            continue

        # Prune noise dirs in-place so os.walk skips them
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
        total_dirs += 1

        for fname in filenames:
            total_files += 1
            fpath = Path(dirpath) / fname
            rel_file = str(fpath.relative_to(root))
            tree.append(rel_file)

            ext = fpath.suffix.lstrip(".").lower() or "no_ext"
            extensions[ext] = extensions.get(ext, 0) + 1

            try:
                size_approx += fpath.stat().st_size
            except OSError:
                pass

            if fname in _SIGNALS:
                key_files.append(rel_file)

    return RepositoryManifest(
        investigation_id=investigation_id,
        root_path=str(root),
        total_files=total_files,
        total_dirs=total_dirs,
        key_files=key_files,
        extensions=extensions,
        directory_tree=tree,
        size_bytes_approx=size_approx,
    )
