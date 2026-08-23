"""Investigation Request data model.

The InvestigationRequest is the complete package sent to the Runtime Engine.
It wraps the Intent with repository information and execution options.

This is the contract between the CLI and the Runtime Engine.
When the Runtime Engine is built, it will accept this exact structure.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from wizard.cli.models.intent import Intent


@dataclass(frozen=True)
class RepositoryInfo:
    """Information about the target repository.

    Attributes:
        path: Absolute path to the repository on disk.
        type: Repository source type — currently only "local".
    """

    path: str
    type: str = "local"

    def to_dict(self) -> dict:
        """Serialize to a plain dictionary."""
        return {
            "path": self.path,
            "type": self.type,
        }


@dataclass(frozen=True)
class RequestOptions:
    """Execution options that control how the Runtime Engine processes the request.

    Attributes:
        budget: Maximum number of tool executions allowed.
        output_format: Desired output format — "markdown" or "json".
        verbose: Whether to show detailed investigation progress.
        quiet: Whether to suppress all output except the final result.
    """

    budget: int = 100
    output_format: str = "markdown"
    verbose: bool = False
    quiet: bool = False

    def to_dict(self) -> dict:
        """Serialize to a plain dictionary."""
        return {
            "budget": self.budget,
            "output_format": self.output_format,
            "verbose": self.verbose,
            "quiet": self.quiet,
        }


@dataclass(frozen=True)
class InvestigationRequest:
    """Complete request package sent to the Runtime Engine.

    This is the CLI's final output — the structured message that crosses
    the boundary between the CLI and the Runtime Engine.

    Attributes:
        repository: Information about the target repository.
        intent: The structured user intent.
        options: Execution options.
    """

    repository: RepositoryInfo
    intent: Intent
    options: RequestOptions = field(default_factory=RequestOptions)

    def to_dict(self) -> dict:
        """Serialize the full request to a plain dictionary."""
        return {
            "repository": self.repository.to_dict(),
            "intent": self.intent.to_dict(),
            "options": self.options.to_dict(),
        }
