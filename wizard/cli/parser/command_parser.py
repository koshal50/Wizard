"""Command parser — Step 1 of the CLI pipeline.

Validates that a command family and target combination is supported.
Contains the canonical registry of all valid targets per command family.

This module has ZERO domain knowledge. It does not know what "architecture"
means — it only knows that "architecture" is a valid string for the
"investigate" command family.
"""

from __future__ import annotations

from difflib import get_close_matches


# ---------------------------------------------------------------------------
# Canonical Target Registry
# ---------------------------------------------------------------------------
# Every valid (command_family, target) pair lives here.
# When new targets are added to the system, they are added here — nowhere else.

COMMAND_TARGETS: dict[str, list[str]] = {
    "investigate": [
        "architecture",
        "runtime",
        "deployment",
        "authentication",
        "api",
        "security",
        "build",
    ],
    # Future command families — targets defined by cli.md
    "verify": [
        "runtime",
        "dependencies",
        "containers",
        "ci",
        "security",
        "deployment",
        "api",
    ],
    "report": [],  # report takes no target, only options
    "explain": [
        "runtime",
        "architecture",
        "dependencies",
        "deployment",
        "security",
    ],
}

# All recognized command families
VALID_COMMANDS: list[str] = list(COMMAND_TARGETS.keys())


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class CommandValidationError(Exception):
    """Raised when a command or target is invalid.

    Attributes:
        message: Human-readable error message.
        suggestions: List of suggested corrections (may be empty).
    """

    def __init__(self, message: str, suggestions: list[str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.suggestions = suggestions or []


def validate_command(command: str) -> None:
    """Validate that a command family is recognized.

    Args:
        command: The command family string (e.g. "investigate").

    Raises:
        CommandValidationError: If the command is not recognized.
    """
    if command not in VALID_COMMANDS:
        suggestions = get_close_matches(command, VALID_COMMANDS, n=1, cutoff=0.5)
        hint = f' Did you mean "{suggestions[0]}"?' if suggestions else ""
        raise CommandValidationError(
            f'Unknown command "{command}".{hint}\n'
            f"Valid commands: {', '.join(VALID_COMMANDS)}",
            suggestions=suggestions,
        )


def validate_target(command: str, target: str) -> None:
    """Validate that a target is valid for a given command family.

    Args:
        command: The command family (must already be validated).
        target: The target string to validate.

    Raises:
        CommandValidationError: If the target is not valid for this command.
    """
    valid_targets = COMMAND_TARGETS.get(command, [])

    # Commands with no targets (e.g. "report") should not receive one
    if not valid_targets:
        if target:
            raise CommandValidationError(
                f'The "{command}" command does not accept a target.\n'
                f"Usage: wizard {command} [options]"
            )
        return

    # Target is required for commands that have targets
    if not target:
        raise CommandValidationError(
            f'The "{command}" command requires a target.\n'
            f'Valid targets for "{command}": {", ".join(valid_targets)}',
            suggestions=valid_targets,
        )

    if target not in valid_targets:
        suggestions = get_close_matches(target, valid_targets, n=1, cutoff=0.4)
        hint = f' Did you mean "{suggestions[0]}"?' if suggestions else ""
        raise CommandValidationError(
            f'"{target}" is not a valid target for "{command}".{hint}\n'
            f'Valid targets for "{command}": {", ".join(valid_targets)}',
            suggestions=suggestions,
        )


def get_valid_targets(command: str) -> list[str]:
    """Return the list of valid targets for a command family.

    Args:
        command: The command family.

    Returns:
        List of valid target strings. Empty list for target-less commands.
    """
    return list(COMMAND_TARGETS.get(command, []))
