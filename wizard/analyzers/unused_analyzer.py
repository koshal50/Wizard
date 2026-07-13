"""Unused dependency heuristic analyzer.

Compares declared dependencies against project imports to identify
dependencies that MIGHT be unused. Results are clearly labeled as heuristic.
"""

from __future__ import annotations

from wizard.models.dependency_result import Dependency, UnusedDependencyHint
from wizard.utils.constants import PACKAGE_IMPORT_MAP


def analyze(
    dependencies: list[Dependency],
    project_imports: dict[str, set[str]],
) -> list[UnusedDependencyHint]:
    """Identify potentially unused dependencies.

    Compares declared dependencies against extracted imports.
    Only analyzes Python and JavaScript ecosystems where package-to-import
    mapping is reliable.

    Args:
        dependencies: All parsed dependencies.
        project_imports: Dict of language → set of imported module names.

    Returns:
        List of UnusedDependencyHint findings.
    """
    hints: list[UnusedDependencyHint] = []

    python_imports = project_imports.get("Python", set())
    js_imports = project_imports.get("JavaScript", set())

    for dep in dependencies:
        source = dep.source_file.lower()

        # Python dependencies
        if source in ("requirements.txt", "pyproject.toml", "pipfile") or "requirements" in source:
            if python_imports and _is_python_dep_unused(dep.name, python_imports):
                hints.append(UnusedDependencyHint(
                    name=dep.name,
                    declared_in=dep.source_file,
                    confidence="low",
                    note=_get_python_unused_note(dep.name),
                ))

        # Node.js dependencies
        elif source == "package.json":
            if js_imports and _is_js_dep_unused(dep.name, js_imports):
                hints.append(UnusedDependencyHint(
                    name=dep.name,
                    declared_in=dep.source_file,
                    confidence="low",
                    note=_get_js_unused_note(dep.name),
                ))

    # Sort by name
    hints.sort(key=lambda h: h.name.lower())

    return hints


def _is_python_dep_unused(package_name: str, imports: set[str]) -> bool:
    """Check if a Python package appears unused based on imports."""
    name_lower = package_name.lower()

    # Skip commonly used packages that may not show up as imports
    skip_packages = {
        "pip", "setuptools", "wheel", "twine", "build", "pre-commit",
        "black", "flake8", "pylint", "mypy", "ruff", "isort",
        "pytest", "pytest-cov", "pytest-xdist", "tox", "nox",
        "rich-click", "tomli", "tomllib",
    }
    if name_lower in skip_packages:
        return False

    # Check direct import match (e.g., "requests" → "requests")
    import_name = name_lower.replace("-", "_")
    if import_name in {i.lower() for i in imports}:
        return False

    # Check known package→import mapping (e.g., "Pillow" → "PIL")
    mapped_import = PACKAGE_IMPORT_MAP.get(name_lower)
    if mapped_import and mapped_import.lower() in {i.lower() for i in imports}:
        return False

    return True


def _is_js_dep_unused(package_name: str, imports: set[str]) -> bool:
    """Check if a Node.js package appears unused based on imports."""
    name_lower = package_name.lower()

    # Skip tool/config packages that are used indirectly
    skip_packages = {
        "typescript", "eslint", "prettier", "webpack", "vite",
        "jest", "mocha", "ts-node", "nodemon", "babel",
        "@types/", "postcss", "autoprefixer", "tailwindcss",
    }
    if any(name_lower.startswith(skip) for skip in skip_packages):
        return False

    # Check if the package is in imports
    if package_name in imports or name_lower in {i.lower() for i in imports}:
        return False

    return True


def _get_python_unused_note(package_name: str) -> str:
    """Generate a note for unused Python dependency."""
    name_lower = package_name.lower()

    if any(x in name_lower for x in ("plugin", "backend", "driver", "adapter")):
        return "May be used as a plugin or backend that is loaded dynamically."
    if any(x in name_lower for x in ("types-", "stubs")):
        return "Type stubs package — used by type checkers, not imported directly."

    return "Heuristic finding — import may use a different name or be used indirectly."


def _get_js_unused_note(package_name: str) -> str:
    """Generate a note for unused Node.js dependency."""
    if package_name.startswith("@types/"):
        return "TypeScript type definitions — not imported directly."

    return "Heuristic finding — package may be used via configuration or plugins."
