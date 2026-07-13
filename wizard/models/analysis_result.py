"""Data models for the `wizard analyze` command results.

All models are dataclasses for easy serialization and structured access.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RepoInfo:
    """Basic repository information."""

    project_name: str
    root_directory: str
    repo_type: str | None = None  # "git", "svn", etc.
    git_initialized: bool = False
    git_branch: str | None = None
    git_remote_url: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class LanguageInfo:
    """Detected programming language."""

    name: str
    file_count: int
    percentage: float
    is_primary: bool = False
    extensions: list[str] = field(default_factory=list)


@dataclass
class FrameworkInfo:
    """Detected framework."""

    name: str
    ecosystem: str  # "Python", "JavaScript", etc.
    confidence: str = "high"  # "high", "medium", "low"
    detection_source: str = ""  # What triggered the detection


@dataclass
class PackageManagerInfo:
    """Detected package manager."""

    name: str
    ecosystem: str
    manifest_files: list[str] = field(default_factory=list)


@dataclass
class ProjectStructure:
    """Summary of project file/directory structure."""

    total_directories: int = 0
    total_files: int = 0
    source_files: int = 0
    documentation_files: int = 0
    configuration_files: int = 0
    template_files: int = 0
    static_assets: int = 0
    test_files: int = 0


@dataclass
class ConfigFileInfo:
    """A detected configuration file."""

    name: str
    path: str
    category: str  # "CI/CD", "Packaging", etc.


@dataclass
class HealthCheck:
    """A single repository health check result."""

    check_id: str
    name: str
    passed: bool
    message: str = ""


@dataclass
class Warning:
    """A non-invasive observation about the repository."""

    severity: str  # "info", "warning", "suggestion"
    category: str  # "documentation", "testing", "structure", etc.
    message: str


@dataclass
class RepoStatistics:
    """Aggregate repository statistics."""

    total_files: int = 0
    total_directories: int = 0
    source_file_count: int = 0
    total_size_bytes: int = 0
    largest_directories: list[tuple[str, int]] = field(default_factory=list)
    language_distribution: list[LanguageInfo] = field(default_factory=list)


@dataclass
class AnalysisResult:
    """Top-level container for all analysis results."""

    repo_info: RepoInfo | None = None
    languages: list[LanguageInfo] = field(default_factory=list)
    frameworks: list[FrameworkInfo] = field(default_factory=list)
    package_managers: list[PackageManagerInfo] = field(default_factory=list)
    structure: ProjectStructure = field(default_factory=ProjectStructure)
    config_files: list[ConfigFileInfo] = field(default_factory=list)
    health_checks: list[HealthCheck] = field(default_factory=list)
    warnings: list[Warning] = field(default_factory=list)
    statistics: RepoStatistics = field(default_factory=RepoStatistics)
    errors: list[str] = field(default_factory=list)

    @property
    def health_score(self) -> float:
        """Calculate overall health score as percentage."""
        if not self.health_checks:
            return 0.0
        passed = sum(1 for check in self.health_checks if check.passed)
        return round((passed / len(self.health_checks)) * 100, 1)

    @property
    def primary_language(self) -> str | None:
        """Get the primary detected language."""
        for lang in self.languages:
            if lang.is_primary:
                return lang.name
        return self.languages[0].name if self.languages else None
