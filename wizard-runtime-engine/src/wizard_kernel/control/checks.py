"""Evaluate explicit expectations against actual check-scoped observations."""
from __future__ import annotations

from wizard_kernel.contracts.verification import Assertion, CheckSpec

_SOURCES = {
    "repository": {"read_file", "path_exists"}, "command": {"execute_command"},
    "process": {"start_process", "read_process", "check_port", "kill_process"},
    "http": {"http_request"},
    "browser": {"browser_navigate", "browser_snapshot", "browser_extract", "browser_click", "browser_type", "browser_fill_form", "browser_back", "browser_assertion"},
}


def evaluate(check: CheckSpec, observations: list) -> list[dict]:
    results = []
    for assertion in check.assertions:
        try:
            results.extend(_evaluate(check.model_copy(update={'assertions': [assertion]}), observations))
        except (AttributeError, TypeError, ValueError, KeyError) as exc:
            results.append({'assertion': assertion.model_dump(), 'verdict': 'evaluation_error',
                            'actual': None, 'observation_id': None,
                            'reason': f'Evidence evaluation failed: {type(exc).__name__}'})
    return results


def _evaluate(check: CheckSpec, observations: list) -> list[dict]:
    # Repository reads are immutable evidence shared within this investigation.
    # Runtime/browser observations retain their check and submission boundaries.
    scoped = [o for o in observations if o.goal_id == check.id or o.source_tool in _SOURCES['repository']]
    results = []
    process_commands = {}
    for obs in scoped:
        if obs.source_tool not in _SOURCES['process']:
            continue
        data = obs.payload.get("data") or {}
        handle = data.get("handle_id") or (obs.payload.get("meta") or {}).get("handle_id")
        if handle and data.get("command"):
            process_commands[handle] = data["command"]
    for assertion in check.assertions:
        submitted = False
        candidate = None
        for obs in scoped:
            if obs.source_tool not in _SOURCES[assertion.source]:
                continue
            payload = obs.payload
            data = payload.get("data") or {}
            if obs.source_tool == "browser_click" and payload.get("ok") and data.get("submitted_form"):
                submitted = True
            if obs.source_tool in {"browser_navigate", "browser_back"}:
                candidate = None
                submitted = False
            if (assertion.source == "http" and data.get("status_code") is None
                    or assertion.source == "browser" and not obs.success and obs.source_tool != "browser_assertion"
                    or assertion.source == "process" and assertion.field == "active"
                    and (obs.source_tool == "kill_process" or data.get("is_running") is False)):
                candidate = None
                if assertion.source == "browser":
                    submitted = False
                continue
            if assertion.after_submission and not submitted:
                continue
            actual_data = data.get("page_observation") or data
            target = str(actual_data.get("url") or data.get("path") or data.get("command")
                         or (payload.get("meta") or {}).get("command")
                         or process_commands.get((payload.get("meta") or {}).get("handle_id"), ""))
            expected_target = assertion.target
            if assertion.source == "repository":
                # Executor paths are native Windows paths; contracts use portable
                # repository paths. Separator differences do not change identity.
                target = target.replace("\\", "/")
                expected_target = expected_target.replace("\\", "/")
            if expected_target and target != expected_target and not (
                    assertion.source == 'repository' and expected_target == obs.id):
                continue
            if assertion.source == 'repository' and not obs.success:
                continue
            if assertion.field in actual_data:
                candidate = (obs, actual_data[assertion.field])
            elif assertion.source == 'repository' and assertion.field == 'exists' and obs.source_tool == 'read_file':
                # A successful read directly measures existence, even for older
                # persisted observations without an explicit exists field.
                candidate = (obs, True)
            elif assertion.field in payload:
                candidate = (obs, payload[assertion.field])
            elif assertion.source == 'repository' and (
                    obs.source_tool == 'read_file' and assertion.field == 'content'
                    or obs.source_tool == 'path_exists' and assertion.field == 'exists'):
                candidate = (obs, None)
        expectation = assertion.model_dump()
        if candidate is None:
            results.append({"assertion": expectation, "verdict": "unverified", "actual": None,
                            "observation_id": None, "reason": f"No compatible observation: {assertion.source}.{assertion.field} for {assertion.target or 'this check'} requires accessible successful evidence"})
            continue
        obs, actual = candidate
        text = str(actual).lower() if isinstance(actual, bool) else str(actual)
        expected = assertion.expected
        if actual is None or isinstance(actual, (dict, list)):
            results.append({"assertion": expectation, "verdict": "evaluation_error", "actual": None,
                            "observation_id": obs.id, "reason": f"Invalid evidence field {assertion.field}: expected scalar value"})
            continue
        matched_text = text if assertion.case_sensitive else text.casefold()
        matched_expected = expected if assertion.case_sensitive else expected.casefold()
        passed = {"equals": matched_text == matched_expected, "contains": matched_expected in matched_text,
                  "not_contains": matched_expected not in matched_text}[assertion.operator]
        # A failed browser operation cannot prove a page assertion. HTTP error
        # statuses are actual responses and can prove an explicitly negative check.
        if assertion.source == "browser" and not obs.success and obs.source_tool != "browser_assertion":
            passed = False
        offset = max(0, matched_text.find(matched_expected) - 100) if passed and assertion.operator == "contains" else 0
        results.append({"assertion": expectation, "verdict": "passed" if passed else "failed",
                        "actual": text[offset:offset + 2000], "observation_id": obs.id,
                        "reason": '' if passed else f'Observed {assertion.field} does not satisfy {assertion.operator} {expected}'})
    return results


def verdict(results: list[dict]) -> str:
    if any(r['verdict'] == 'evaluation_error' for r in results):
        return 'evaluation_error'
    if any(r["verdict"] == "failed" for r in results):
        return "failed"
    if not results or any(r["verdict"] == "unverified" for r in results):
        return "unverified"
    return "passed" if all(r["verdict"] == "passed" for r in results) else "failed"
