"""Data models for the `wizard dependency-insights` command results.

All models are dataclasses for easy serialization and structured access.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class DependencyGroup(str, Enum):
    """Dependency categorization."""

    PRODUCTION = "production"
    DEVELOPMENT = "development"
    TESTING = "testing"
    OPTIONAL = "optional"
    BUILD = "build"
    PEER = "peer"
    UNKNOWN = "unknown"


@dataclass
class Dependency:
    """A single parsed dependency."""

    name: str
    version_constraint: str = "*"  # As declared in the manifest
    group: DependencyGroup = DependencyGroup.PRODUCTION
    source_file: str = ""  # Which manifest it came from
    extras: list[str] = field(default_factory=list)


@dataclass
class DuplicateDependency:
    """A dependency declared in multiple places."""

    name: str
    locations: list[str] = field(default_factory=list)  # File paths
    versions: list[str] = field(default_factory=list)  # Version strings
    has_conflict: bool = False  # Different versions declared


@dataclass
class MissingDependencyHint:
    """A heuristic suggestion for a possibly missing dependency."""

    import_name: str
    suggested_package: str = ""
    used_in_files: list[str] = field(default_factory=list)
    confidence: str = "low"  # "high", "medium", "low"


@dataclass
class UnusedDependencyHint:
    """A heuristic suggestion for a possibly unused dependency."""

    name: str
    declared_in: str = ""  # Manifest file
    confidence: str = "low"
    note: str = ""  # Explanation (e.g., "may be used as a plugin")


@dataclass
class ManifestIssue:
    """An issue found during manifest validation."""

    file: str
    issue_type: str  # "malformed", "duplicate", "empty", "encoding"
    message: str
    severity: str = "warning"  # "error", "warning", "info"
    line_number: int | None = None


@dataclass
class DependencyRelationship:
    """A direct dependency relationship (no transitive resolution)."""

    package: str
    depends_on: list[str] = field(default_factory=list)
    relationship_type: str = "direct"  # Always "direct" in MVP


@dataclass
class DependencyResult:
    """Top-level container for all dependency analysis results."""

    package_manager: str | None = None
    ecosystem: str | None = None
    manifest_files: list[str] = field(default_factory=list)
    dependencies: list[Dependency] = field(default_factory=list)
    duplicates: list[DuplicateDependency] = field(default_factory=list)
    missing_hints: list[MissingDependencyHint] = field(default_factory=list)
    unused_hints: list[UnusedDependencyHint] = field(default_factory=list)
    manifest_issues: list[ManifestIssue] = field(default_factory=list)
    relationships: list[DependencyRelationship] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def total_dependencies(self) -> int:
        """Total number of unique dependencies."""
        return len({dep.name for dep in self.dependencies})

    @property
    def dependencies_by_group(self) -> dict[str, list[Dependency]]:
        """Group dependencies by their category."""
        groups: dict[str, list[Dependency]] = {}
        for dep in self.dependencies:
            key = dep.group.value
            groups.setdefault(key, []).append(dep)
        return groups

    @property
    def production_count(self) -> int:
        return sum(1 for d in self.dependencies if d.group == DependencyGroup.PRODUCTION)

    @property
    def dev_count(self) -> int:
        return sum(1 for d in self.dependencies if d.group == DependencyGroup.DEVELOPMENT)

    @property
    def test_count(self) -> int:
        return sum(1 for d in self.dependencies if d.group == DependencyGroup.TESTING)
