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
    scoped = [o for o in observations if o.goal_id == check.id]
    results = []
    process_commands = {}
    for obs in scoped:
        data = obs.payload.get("data") or {}
        handle = data.get("handle_id") or (obs.payload.get("meta") or {}).get("handle_id")
        if handle and data.get("command"):
            process_commands[handle] = data["command"]
    for assertion in check.assertions:
        submitted = False
        candidate = None
        for obs in scoped:
            payload = obs.payload
            data = payload.get("data") or {}
            if obs.source_tool == "browser_click" and payload.get("ok") and data.get("submitted_form"):
                submitted = True
            if obs.source_tool not in _SOURCES[assertion.source]:
                continue
            if obs.source_tool in {"browser_navigate", "browser_back"}:
                candidate = None
                submitted = False
            if (assertion.source == "http" and data.get("status_code") is None
                    or assertion.source == "browser" and not obs.success and obs.source_tool != "browser_assertion"
                    or assertion.source == "repository" and not obs.success
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
            if expected_target and target != expected_target:
                continue
            if assertion.field in actual_data:
                candidate = (obs, actual_data[assertion.field])
            elif assertion.field in payload:
                candidate = (obs, payload[assertion.field])
        expectation = assertion.model_dump()
        if candidate is None:
            results.append({"assertion": expectation, "verdict": "unverified", "actual": None,
                            "observation_id": None, "reason": "No compatible observation"})
            continue
        obs, actual = candidate
        text = str(actual).lower() if isinstance(actual, bool) else str(actual)
        expected = assertion.expected
        passed = {"equals": text == expected, "contains": expected in text,
                  "not_contains": expected not in text}[assertion.operator]
        # A failed browser operation cannot prove a page assertion. HTTP error
        # statuses are actual responses and can prove an explicitly negative check.
        if assertion.source == "browser" and not obs.success and obs.source_tool != "browser_assertion":
            passed = False
        offset = max(0, text.find(expected) - 100) if passed and assertion.operator == "contains" else 0
        results.append({"assertion": expectation, "verdict": "passed" if passed else "failed",
                        "actual": text[offset:offset + 2000], "observation_id": obs.id, "reason": ""})
    return results


def verdict(results: list[dict]) -> str:
    if any(r["verdict"] == "failed" for r in results):
        return "failed"
    if not results or any(r["verdict"] == "unverified" for r in results):
        return "unverified"
    return "passed" if all(r["verdict"] == "passed" for r in results) else "failed"
