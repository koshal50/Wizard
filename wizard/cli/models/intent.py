"""Intent data model.

The Intent is the structured representation of what the user wants.
It is command-family agnostic — every command family (investigate, verify,
report, explain) produces the same Intent shape.

The Intent contains no domain knowledge. It does not know what
"architecture" means or how to investigate it. It only knows that
the user asked for it.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Intent:
    """Structured representation of user intent.

    Attributes:
        action: The command family — "investigate", "verify", "report", "explain".
        targets: List of targets the user specified (e.g. ["architecture"]).
        confidence_threshold: The investigation depth implied by the command.
            - "exploratory" for investigate (understanding, not verdict)
            - "standard" for verify (confident pass/fail)
            - "report" for report (generate from existing knowledge)
            - "explanatory" for explain (read from verified knowledge)
    """

    action: str
    targets: list[str] = field(default_factory=list)
    confidence_threshold: str = "exploratory"

    def to_dict(self) -> dict:
        """Serialize Intent to a plain dictionary."""
        return {
            "action": self.action,
            "targets": list(self.targets),
            "confidence_threshold": self.confidence_threshold,
        }
