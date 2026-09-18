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
        urls: Absolute http(s) URLs named by the user, in first-seen order.
            A URL is a target of the *web* plane rather than the file plane,
            which is why it is held separately: it must not be validated
            against COMMAND_TARGETS (no family lists a URL), but it does have
            to reach the Runtime, which is what `api_targets` is for.
        confidence_threshold: The investigation depth implied by the command.
            - "exploratory" for investigate (understanding, not verdict)
            - "standard" for verify (confident pass/fail)
            - "report" for report (generate from existing knowledge)
            - "explanatory" for explain (read from verified knowledge)
    """

    action: str
    targets: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)
    confidence_threshold: str = "exploratory"
    question: str = ""
    """What the user typed, verbatim, when they typed anything.

    Held apart from `targets` because it is a different kind of input. A target
    is a word the command vocabulary already knows ("architecture", "runtime");
    the question is the sentence the user wrote, which may name something no
    target does — "the auth flow", "how payments settle". Parsing the sentence
    into targets is lossy on purpose (see intent_parser), and the loss was total:
    the Runtime was never told what was asked, so a Planner reading its `intent`
    field saw the command family and nothing else, and "investigate the auth
    flow" produced the same plan as a bare `wizard investigate architecture`.
    """

    @property
    def api_targets(self) -> list[str]:
        """The `targets` array to send the Runtime: names then URLs.

        Named targets come first so the file plane is investigated before the
        web plane — and so a run's early events describe the repository, which
        is what the user is usually watching for. The Runtime reads both out
        of the one array (ports/planner.py filters for the http prefix to find
        the browser ones), so this is the single place that decides the order
        and the only place that has to know URLs ride in `targets`.
        """
        return [*self.targets, *self.urls]

    def to_dict(self) -> dict:
        """Serialize Intent to a plain dictionary."""
        return {
            "action": self.action,
            "targets": list(self.targets),
            "urls": list(self.urls),
            "confidence_threshold": self.confidence_threshold,
            "question": self.question,
        }
