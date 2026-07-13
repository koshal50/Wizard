"""Missing dependency heuristic analyzer.

Identifies imports that don't appear in any dependency manifest.
Results are labeled as suggestions, not confirmed issues.
"""

from __future__ import annotations

from wizard.models.dependency_result import Dependency, MissingDependencyHint
from wizard.utils.constants import IMPORT_PACKAGE_MAP, PACKAGE_IMPORT_MAP, PYTHON_STDLIB_MODULES


def analyze(
    dependencies: list[Dependency],
    project_imports: dict[str, set[str]],
) -> list[MissingDependencyHint]:
    """Identify imports that might correspond to undeclared dependencies.

    Args:
        dependencies: All parsed dependencies.
        project_imports: Dict of language → set of imported module names.

    Returns:
        List of MissingDependencyHint suggestions.
    """
    hints: list[MissingDependencyHint] = []

    # Analyze Python imports
    python_imports = project_imports.get("Python", set())
    if python_imports:
        python_deps = {dep.name.lower().replace("-", "_") for dep in dependencies}
        # Also include mapped import names
        for dep in dependencies:
            mapped = PACKAGE_IMPORT_MAP.get(dep.name.lower())
            if mapped:
                python_deps.add(mapped.lower())

        python_hints = _find_missing_python_deps(python_imports, python_deps)
        hints.extend(python_hints)

    # Analyze JavaScript imports
    js_imports = project_imports.get("JavaScript", set())
    if js_imports:
        js_deps = {dep.name.lower() for dep in dependencies}
        js_hints = _find_missing_js_deps(js_imports, js_deps)
        hints.extend(js_hints)

    # Sort by confidence (high first), then name
    confidence_order = {"high": 0, "medium": 1, "low": 2}
    hints.sort(key=lambda h: (confidence_order.get(h.confidence, 3), h.import_name.lower()))

    return hints


def _find_missing_python_deps(
    imports: set[str],
    declared_deps: set[str],
) -> list[MissingDependencyHint]:
    """Find Python imports that aren't in declared dependencies."""
    hints: list[MissingDependencyHint] = []

    for import_name in imports:
        # Skip stdlib modules
        if import_name in PYTHON_STDLIB_MODULES:
            continue

        # Skip private/internal imports
        if import_name.startswith("_"):
            continue

        # Skip very short names likely to be false positives (e.g., 'x', 'e')
        if len(import_name) <= 2:
            continue

        # Skip names containing spaces (from mis-parsed comments/strings)
        if " " in import_name:
            continue

        # Normalize for comparison
        normalized = import_name.lower().replace("-", "_")

        # Check if the import matches any declared dependency
        if normalized in declared_deps:
            continue

        # Skip imports that look like local/project packages
        # (e.g., the project's own package name)
        if normalized in declared_deps or _looks_like_local_package(import_name):
            continue

        # Check reverse mapping (import name → package name)
        suggested_package = IMPORT_PACKAGE_MAP.get(import_name, import_name)

        # Determine confidence
        if suggested_package != import_name:
            confidence = "medium"  # We have a known mapping
        else:
            confidence = "low"  # Just a guess

        hints.append(MissingDependencyHint(
            import_name=import_name,
            suggested_package=suggested_package,
            confidence=confidence,
        ))

    return hints


def _looks_like_local_package(name: str) -> bool:
    """Check if an import name looks like a local/project package.

    Heuristic: if the name matches common project source directory patterns
    or is a generic word not likely to be a PyPI package.
    """
    # Common local package names / false positives from comments
    local_patterns = {
        "wizard", "app", "src", "lib", "core", "main", "config", "utils",
        "tests", "test", "foo", "bar", "baz", "example", "sample",
        "com", "org", "net", "static",
    }
    return name.lower() in local_patterns


def _find_missing_js_deps(
    imports: set[str],
    declared_deps: set[str],
) -> list[MissingDependencyHint]:
    """Find JavaScript imports that aren't in declared dependencies."""
    hints: list[MissingDependencyHint] = []

    # Common Node.js built-in modules to skip
    node_builtins = {
        "fs", "path", "os", "url", "http", "https", "crypto", "stream",
        "util", "events", "buffer", "child_process", "cluster", "dgram",
        "dns", "net", "readline", "tls", "vm", "zlib", "assert",
        "console", "process", "querystring", "string_decoder", "timers",
        "tty", "worker_threads", "perf_hooks",
        # Node.js prefixed
        "node:fs", "node:path", "node:os", "node:url", "node:http",
        "node:https", "node:crypto", "node:stream", "node:util",
    }

    for import_name in imports:
        if import_name in node_builtins:
            continue
        if import_name.startswith("node:"):
            continue

        if import_name.lower() in declared_deps:
            continue

        hints.append(MissingDependencyHint(
            import_name=import_name,
            suggested_package=import_name,
            confidence="low",
        ))

    return hints
