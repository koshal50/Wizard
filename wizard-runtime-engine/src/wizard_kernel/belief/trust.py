"""Trust Engine — belief formula from INVESTIGATION_KERNEL_DESIGN.md §9.

belief      = support / (support + contradict + u0)
disbelief   = contradict / (support + contradict + u0)
uncertainty = 1 - belief - disbelief

Source weights:  execution > config_parse > documentation
Same observation_id never double-counts.
docs-only claims cannot satisfy verify goals (threshold requires execution evidence).
"""
from wizard_kernel.contracts.evidence import Evidence, SourceTier

U0 = 0.1  # prior uncertainty

SOURCE_WEIGHTS: dict[str, float] = {
    "execution":   1.0,
    "config_parse": 0.6,
    "documentation": 0.2,
}


def compute(evidences: list[Evidence]) -> float:
    """Return belief score [0, 1] for a claim given its evidence set."""
    seen_obs: set[str] = set()
    support = contradict = 0.0

    for e in evidences:
        # Deduplicate — same obs_id never counts twice (invariant 2)
        new_obs = [o for o in e.observation_ids if o not in seen_obs]
        if not new_obs:
            continue
        seen_obs.update(new_obs)
        w = SOURCE_WEIGHTS.get(e.source_tier, 0.2) * len(new_obs)
        if e.support_type == "support":
            support += w
        else:
            contradict += w

    return round(support / (support + contradict + U0), 4)


def has_execution_evidence(evidences: list[Evidence]) -> bool:
    """True if at least one piece of execution-tier evidence exists."""
    return any(e.source_tier == "execution" for e in evidences)


def disbelief(evidences: list[Evidence]) -> float:
    seen_obs: set[str] = set()
    contradict = support = 0.0
    for e in evidences:
        new_obs = [o for o in e.observation_ids if o not in seen_obs]
        if not new_obs:
            continue
        seen_obs.update(new_obs)
        w = SOURCE_WEIGHTS.get(e.source_tier, 0.2) * len(new_obs)
        if e.support_type == "contradict":
            contradict += w
        else:
            support += w
    return round(contradict / (support + contradict + U0), 4)


def source_tier_for_tool(tool_name: str) -> SourceTier:
    """Infer evidence source tier from the tool that produced the observation."""
    if tool_name in ("execute_command", "check_port", "start_process", "read_process"):
        return "execution"
    if tool_name in ("read_file", "list_tree", "search_files", "path_exists"):
        return "config_parse"
    return "documentation"
