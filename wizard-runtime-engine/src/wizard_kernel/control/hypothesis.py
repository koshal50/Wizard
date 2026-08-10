"""Hypothesis evaluator — deterministic match of observation vs node hypothesis. Phase 3."""
from typing import Literal
from wizard_kernel.contracts.node import HypothesisKind, Hypothesis, InvestigationNode
from wizard_kernel.contracts.observation import Observation

MatchResult = Literal["expected_success", "expected_failure", "unexpected"]


def evaluate(node: InvestigationNode, obs: Observation) -> MatchResult:
    """Return match result without any LLM call. Only unexpected escalates to Planner."""
    h: Hypothesis = node.hypothesis
    payload = obs.payload

    match h.kind:
        case HypothesisKind.always_success:
            return "expected_success"

        case HypothesisKind.manual_escalate:
            return "unexpected"

        case HypothesisKind.exit_code_in:
            code = payload.get("exit_code")
            if code in h.success_values:
                return "expected_success"
            if code in h.failure_values:
                return "expected_failure"
            return "unexpected"

        case HypothesisKind.stdout_contains:
            stdout: str = payload.get("stdout", "")
            if h.pattern and h.pattern in stdout:
                return "expected_success"
            if h.failure_values and all(v not in stdout for v in h.failure_values):
                return "expected_failure"
            return "unexpected"

        case HypothesisKind.file_exists:
            exists = payload.get("exists", False)
            return "expected_success" if exists else "expected_failure"

        case HypothesisKind.http_status:
            status = payload.get("status_code")
            if status in h.success_values:
                return "expected_success"
            if status in h.failure_values:
                return "expected_failure"
            return "unexpected"

        case HypothesisKind.json_path_equals:
            # payload must carry {"resolved_value": ...}
            resolved = payload.get("resolved_value")
            target = h.success_values[0] if h.success_values else None
            if resolved == target:
                return "expected_success"
            if resolved in h.failure_values:
                return "expected_failure"
            return "unexpected"

        case _:
            return "unexpected"
