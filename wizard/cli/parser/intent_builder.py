"""Intent builder — Step 2 of the CLI pipeline.

Converts validated command components into a structured Intent object.
This is the bridge between raw parsed strings and the typed Intent model.

The builder maps each command family to its appropriate confidence threshold
as defined in cli.md:
    - investigate → "exploratory"  (understanding, not verdict)
    - verify     → "standard"     (rigorous pass/fail)
    - report     → "report"       (generate from existing knowledge)
    - explain    → "explanatory"  (read from verified knowledge)
"""

from __future__ import annotations

from wizard.cli.models.intent import Intent


# ---------------------------------------------------------------------------
# Confidence Threshold Mapping
# ---------------------------------------------------------------------------
# Each command family implies a different depth of investigation.
# This mapping is the only "knowledge" the intent builder has.

CONFIDENCE_THRESHOLDS: dict[str, str] = {
    "investigate": "exploratory",
    "verify": "standard",
    "report": "report",
    "explain": "explanatory",
}


def build_intent(action: str, target: str | None = None) -> Intent:
    """Build an Intent from validated command components.

    Args:
        action: The command family (e.g. "investigate"). Must already be
                validated by command_parser.validate_command().
        target: The target string (e.g. "architecture"). May be None for
                target-less commands like "report".

    Returns:
        A fully constructed Intent object ready for request assembly.
    """
    targets = [target] if target else []
    confidence = CONFIDENCE_THRESHOLDS.get(action, "exploratory")

    return Intent(
        action=action,
        targets=targets,
        confidence_threshold=confidence,
    )
