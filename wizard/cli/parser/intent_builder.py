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
from wizard.cli.parser.command_parser import COMMAND_TARGETS


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


def build_intent(
    action: str,
    target: str | None = None,
    targets: list[str] | None = None,
    urls: list[str] | None = None,
    question: str = "",
) -> Intent:
    """Build an Intent from validated command components.

    Args:
        action: The command family (e.g. "investigate"). Must already be
                validated by command_parser.validate_command().
        target: A single target (e.g. "architecture"). May be None for
                target-less commands like "report". Kept for the many callers
                that pass one target.
        targets: Additional targets, from parsing the user's free text. These
                are UNIONED with `target` rather than replacing it, and are
                assumed already validated by intent_parser.validate_parsed —
                any that are not valid for `action` are dropped here rather
                than raising, because one unrecognised word in a sentence must
                not fail an otherwise good request.
        urls: Absolute http(s) URLs the user named. Carried as web-plane
                targets (Intent.urls), never validated as command targets.
        question: The user's free text, verbatim. Carried through unchanged and
                never validated: it is not a command, it is what the user said,
                and the Planner is the only thing entitled to read it.

    Returns:
        A fully constructed Intent object ready for request assembly.

    Deduplication preserves order and lets the menu's target stay first, so a
    user who selected "api" and then typed "and the api routes" investigates
    "api" once, not twice.
    """
    ordered: list[str] = []
    for candidate in ([target] if target else []) + list(targets or []):
        if candidate and candidate not in ordered:
            ordered.append(candidate)

    valid = COMMAND_TARGETS.get(action, [])
    if valid:
        ordered = [t for t in ordered if t in valid]
    elif ordered:
        # A family that accepts no target (report) must not be handed one —
        # validate_target raises on exactly this, so drop it here instead.
        ordered = []

    unique_urls: list[str] = []
    for url in urls or []:
        if url and url not in unique_urls:
            unique_urls.append(url)

    confidence = CONFIDENCE_THRESHOLDS.get(action, "exploratory")

    return Intent(
        action=action,
        targets=ordered,
        urls=unique_urls,
        confidence_threshold=confidence,
        question=question.strip(),
    )
