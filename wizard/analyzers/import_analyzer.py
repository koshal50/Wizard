"""Static import extraction analyzer.

Extracts import statements from source files to support
unused/missing dependency heuristics. Does NOT execute any code.
"""

from __future__ import annotations

import re
from pathlib import Path

from wizard.utils.constants import EXTENSION_LANGUAGE_MAP
from wizard.utils.file_utils import safe_read_file, walk_project


def extract_imports(project_path: Path) -> dict[str, set[str]]:
    """Extract imported module/package names from source files.

    Args:
        project_path: Resolved project root.

    Returns:
        Dict mapping language → set of imported top-level module names.
    """
    files = walk_project(project_path)
    result: dict[str, set[str]] = {}

    for file_path in files:
        ext = file_path.suffix.lower()
        lang = EXTENSION_LANGUAGE_MAP.get(ext)

        if lang == "Python":
            imports = _extract_python_imports(file_path)
            result.setdefault("Python", set()).update(imports)
        elif lang in ("JavaScript", "TypeScript"):
            imports = _extract_js_imports(file_path)
            result.setdefault("JavaScript", set()).update(imports)
        elif lang == "Java":
            imports = _extract_java_imports(file_path)
            result.setdefault("Java", set()).update(imports)

    return result


def _extract_python_imports(file_path: Path) -> set[str]:
    """Extract top-level module names from Python imports.

    Handles:
        import foo
        import foo.bar
        from foo import bar
        from foo.bar import baz
    """
    content = safe_read_file(file_path)
    if not content:
        return set()

    imports: set[str] = set()

    for line in content.splitlines():
        line = line.strip()

        # Skip comments and strings
        if line.startswith("#") or line.startswith('"""') or line.startswith("'''"):
            continue

        # import foo / import foo.bar / import foo, bar
        match = re.match(r'^import\s+(.+)', line)
        if match:
            for module in match.group(1).split(","):
                module = module.strip().split(" as ")[0].strip()
                top_level = module.split(".")[0]
                if top_level:
                    imports.add(top_level)
            continue

        # from foo import bar / from foo.bar import baz
        match = re.match(r'^from\s+([\w.]+)\s+import', line)
        if match:
            top_level = match.group(1).split(".")[0]
            if top_level:
                imports.add(top_level)

    return imports


def _extract_js_imports(file_path: Path) -> set[str]:
    """Extract package names from JavaScript/TypeScript imports.

    Handles:
        import ... from 'package'
        import ... from "package"
        const x = require('package')
        require("package")
    """
    content = safe_read_file(file_path)
    if not content:
        return set()

    imports: set[str] = set()

    # ES module imports: import ... from 'package'
    for match in re.finditer(r'''(?:import|export)\s+.*?from\s+['"]([^'"]+)['"]''', content):
        pkg = _normalize_js_package(match.group(1))
        if pkg:
            imports.add(pkg)

    # CommonJS require: require('package')
    for match in re.finditer(r'''require\s*\(\s*['"]([^'"]+)['"]\s*\)''', content):
        pkg = _normalize_js_package(match.group(1))
        if pkg:
            imports.add(pkg)

    # Dynamic import: import('package')
    for match in re.finditer(r'''import\s*\(\s*['"]([^'"]+)['"]\s*\)''', content):
        pkg = _normalize_js_package(match.group(1))
        if pkg:
            imports.add(pkg)

    return imports


def _normalize_js_package(import_path: str) -> str | None:
    """Normalize a JS import path to a package name.

    './local' → None (local import)
    '../local' → None (local import)
    'lodash' → 'lodash'
    'lodash/fp' → 'lodash'
    '@scope/pkg' → '@scope/pkg'
    '@scope/pkg/util' → '@scope/pkg'
    """
    if import_path.startswith("."):
        return None  # Local import

    parts = import_path.split("/")

    if import_path.startswith("@") and len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"
    else:
        return parts[0]


def _extract_java_imports(file_path: Path) -> set[str]:
    """Extract package names from Java import statements.

    Handles:
        import com.example.foo.Bar;
        import static com.example.foo.Bar.method;
    """
    content = safe_read_file(file_path)
    if not content:
        return set()

    imports: set[str] = set()

    for match in re.finditer(r'^import\s+(?:static\s+)?([a-zA-Z][\w.]*)', content, re.MULTILINE):
        full_import = match.group(1)
        # Use top two levels as the "package" (e.g., "com.google")
        parts = full_import.split(".")
        if len(parts) >= 2:
            imports.add(f"{parts[0]}.{parts[1]}")
        elif parts:
            imports.add(parts[0])

    return imports
