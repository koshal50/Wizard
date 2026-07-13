"""Abstract base parser for dependency manifest files.

All ecosystem-specific parsers inherit from this base.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from wizard.models.dependency_result import Dependency, ManifestIssue


class BaseParser(ABC):
    """Base class for dependency file parsers.

    Each parser handles a specific manifest format and extracts
    dependency declarations without installing or resolving anything.
    """

    @property
    @abstractmethod
    def ecosystem(self) -> str:
        """The ecosystem this parser handles (e.g., 'Python', 'Node.js')."""

    @property
    @abstractmethod
    def supported_files(self) -> list[str]:
        """List of filenames this parser can handle."""

    def can_parse(self, filename: str) -> bool:
        """Check if this parser supports a given filename."""
        return filename in self.supported_files

    @abstractmethod
    def parse(self, file_path: Path) -> list[Dependency]:
        """Parse a manifest file and extract dependencies.

        Args:
            file_path: Absolute path to the manifest file.

        Returns:
            List of parsed Dependency objects.

        Raises:
            Should not raise — errors should be caught internally
            and reported via validate().
        """

    def validate(self, file_path: Path) -> list[ManifestIssue]:
        """Validate a manifest file for common issues.

        Args:
            file_path: Absolute path to the manifest file.

        Returns:
            List of ManifestIssue objects for any problems found.
        """
        issues: list[ManifestIssue] = []
        rel_path = file_path.name

        # Check if file is empty
        try:
            content = file_path.read_text(encoding="utf-8").strip()
            if not content:
                issues.append(ManifestIssue(
                    file=rel_path,
                    issue_type="empty",
                    message=f"{rel_path} is empty.",
                    severity="warning",
                ))
        except UnicodeDecodeError:
            issues.append(ManifestIssue(
                file=rel_path,
                issue_type="encoding",
                message=f"{rel_path} has encoding issues (not valid UTF-8).",
                severity="error",
            ))
        except OSError as e:
            issues.append(ManifestIssue(
                file=rel_path,
                issue_type="unreadable",
                message=f"Cannot read {rel_path}: {e}",
                severity="error",
            ))

        return issues
