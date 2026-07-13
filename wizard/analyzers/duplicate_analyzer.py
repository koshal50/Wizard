"""Duplicate dependency detection analyzer.

Identifies dependencies declared in multiple manifest files
or duplicated within a single manifest.
"""

from __future__ import annotations

from wizard.models.dependency_result import Dependency, DuplicateDependency


def analyze(dependencies: list[Dependency]) -> list[DuplicateDependency]:
    """Find duplicate dependency declarations.

    A dependency is considered duplicate if:
    - It appears in multiple manifest files
    - It appears multiple times in the same manifest with different versions

    Args:
        dependencies: All parsed dependencies.

    Returns:
        List of DuplicateDependency findings.
    """
    # Group by normalized package name
    by_name: dict[str, list[Dependency]] = {}
    for dep in dependencies:
        key = dep.name.lower().replace("-", "_").replace(".", "_")
        by_name.setdefault(key, []).append(dep)

    duplicates: list[DuplicateDependency] = []

    for key, dep_list in by_name.items():
        if len(dep_list) <= 1:
            continue

        # Check if they come from different files or have conflicting versions
        locations = list({dep.source_file for dep in dep_list})
        versions = list({dep.version_constraint for dep in dep_list})

        # Only report if from different files or truly different versions
        if len(locations) > 1 or len(versions) > 1:
            has_conflict = len(versions) > 1 and "*" not in versions

            duplicates.append(DuplicateDependency(
                name=dep_list[0].name,  # Use first occurrence's casing
                locations=locations,
                versions=versions,
                has_conflict=has_conflict,
            ))

    # Sort by name for consistent output
    duplicates.sort(key=lambda d: d.name.lower())

    return duplicates
