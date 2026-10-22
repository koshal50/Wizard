"""Admission of one bounded plan delta; no execution or provider authority."""
import hashlib
import json

from wizard_kernel.contracts.verification import VerificationSpec


def admit(original, plan, results, observations, *, capabilities, eligible_ids=None):
    if not plan.tasks:
        return original, [], {}
    known = {obs.id for obs in observations}
    if not plan.observation_ids or not set(plan.observation_ids) <= known:
        raise ValueError("Recovery must cite actual observation IDs")
    by_id = {check.id: check for check in original.checks}
    additions, dependencies = [], {}
    seen = {hashlib.sha256(json.dumps({"description": c.description.casefold(),
            "assertions": [a.model_dump() for a in c.assertions]}, sort_keys=True).encode()).hexdigest()
            for c in original.checks}
    for task in plan.tasks:
        check = task.check
        if eligible_ids is not None and task.goal_id not in eligible_ids:
            raise ValueError("Recovery must address an eligible missing outcome")
        if task.goal_id not in by_id or check.id in by_id or check.id in {c.id for c in additions}:
            raise ValueError("Recovery must address an existing goal with unique helper IDs")
        required = set(check.capabilities) | {a.source for a in check.assertions}
        if required - capabilities:
            raise ValueError("Recovery cannot escalate execution capabilities")
        parent_sources = set(by_id[task.goal_id].capabilities) | {a.source for a in by_id[task.goal_id].assertions}
        if parent_sources - {"repository"} and required <= {"repository"}:
            raise ValueError("Static helper checks cannot replace missing runtime evidence")
        key = hashlib.sha256(json.dumps({"description": check.description.casefold(),
            "assertions": [a.model_dump() for a in check.assertions]}, sort_keys=True).encode()).hexdigest()
        if key in seen:
            raise ValueError("Recovery repeats an unchanged check")
        seen.add(key)
        additions.append(check)
        dependencies.setdefault(task.goal_id, []).append(check.id)
    added_ids = {c.id for c in additions}
    for check in additions:
        if any(dep not in added_ids and results.get(dep, {}).get("status") != "passed" for dep in check.depends_on):
            raise ValueError("Recovery helpers may depend only on helpers or passed checks")
    checks = [c.model_copy(update={"depends_on": list(dict.fromkeys(c.depends_on + dependencies.get(c.id, [])))})
              for c in original.checks] + additions
    merged = VerificationSpec.model_validate({"checks": [c.model_dump() for c in checks]})
    return merged, additions, dependencies


def next_ready(pending, results):
    """Dependencies first, stable insertion order; no probabilistic scheduler."""
    return next((check for check in pending
                 if all(results.get(dep, {}).get("status") == "passed" for dep in check.depends_on)), None)
