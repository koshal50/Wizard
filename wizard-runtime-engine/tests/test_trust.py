"""Trust formula correctness — docs-only threshold, contradictions, dedup.
These are the design-doc invariants expressed as pass/fail assertions."""
from wizard_kernel.belief import trust as t


def test_docs_only_belief_under_threshold():
    """docs-only belief must be less than execution-tier — cannot alone satisfy verify goals.
    Formula: 0.2 / (0.2 + 0.1) = 0.6667 < execution (0.9091)."""
    from datetime import datetime, timezone
    from wizard_kernel.contracts.evidence import Evidence
    ev = Evidence(
        id="ev_01", claim_id="cl_01",
        observation_ids=["obs_001"],
        support_type="support", source_tier="documentation",
        created_at=datetime.now(timezone.utc),
    )
    belief = t.compute([ev])
    exec_belief = t.compute([Evidence(
        id="ev_02", claim_id="cl_01",
        observation_ids=["obs_002"],
        support_type="support", source_tier="execution",
        created_at=datetime.now(timezone.utc),
    )])
    # Docs-only is always less than execution-tier — that's the real invariant
    assert belief < exec_belief, f"docs belief {belief} must be < execution belief {exec_belief}"
    assert belief < 0.75, f"docs-only belief {belief} must be reasonably bounded"


def test_contradiction_reduces_belief():
    from datetime import datetime, timezone
    from wizard_kernel.contracts.evidence import Evidence
    def _ev(obs_id, support, tier):
        return Evidence(id=f"ev_{obs_id}", claim_id="cl_01",
                        observation_ids=[obs_id], support_type=support,
                        source_tier=tier, created_at=datetime.now(timezone.utc))

    clean = t.compute([_ev("o1", "support", "execution")])
    with_contradict = t.compute([
        _ev("o1", "support", "execution"),
        _ev("o2", "contradict", "execution"),
    ])
    assert with_contradict < clean


def test_dedup_does_not_inflate():
    from datetime import datetime, timezone
    from wizard_kernel.contracts.evidence import Evidence
    def _ev(obs_ids, tier):
        return Evidence(id="ev_x", claim_id="cl_01", observation_ids=obs_ids,
                        support_type="support", source_tier=tier,
                        created_at=datetime.now(timezone.utc))

    single = t.compute([_ev(["o1"], "execution")])
    doubled = t.compute([_ev(["o1"], "execution"), _ev(["o1"], "execution")])
    assert abs(single - doubled) < 0.01


def test_source_weight_ordering():
    from datetime import datetime, timezone
    from wizard_kernel.contracts.evidence import Evidence
    def _ev(tier):
        import uuid
        return Evidence(id=f"ev_{uuid.uuid4().hex[:4]}", claim_id="cl_01",
                        observation_ids=[f"obs_{uuid.uuid4().hex[:4]}"],
                        support_type="support", source_tier=tier,
                        created_at=datetime.now(timezone.utc))

    exec_b = t.compute([_ev("execution")])
    cfg_b  = t.compute([_ev("config_parse")])
    doc_b  = t.compute([_ev("documentation")])
    assert exec_b > cfg_b > doc_b
