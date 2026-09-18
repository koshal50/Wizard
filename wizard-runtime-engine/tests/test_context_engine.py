"""Context Engine tests — the read-only projection layer (architecture §5–§22).

Covers each stage in isolation (sections, packager, token budget/KV cache, cache,
audit, interceptor, orchestrator) plus an end-to-end assertion that a real loop
run drives the engine and audits every context supply.
"""
from datetime import datetime, timezone

import pytest

from wizard_kernel.belief.knowledge_graph import KnowledgeGraph
from wizard_kernel.contracts.node import Hypothesis, HypothesisKind, InvestigationNode
from wizard_kernel.contracts.observation import Observation
from wizard_kernel.context.audit import CONTEXT_SUPPLIED, ContextAudit
from wizard_kernel.context.budget import TokenBudget
from wizard_kernel.context.cache import ContextCache
from wizard_kernel.context.engine import ContextEngine
from wizard_kernel.context.interceptor import Interceptor, InterceptResult
from wizard_kernel.context.packager import Packager
from wizard_kernel.context.sections import ContextSection, estimate_tokens
from wizard_kernel.control.goals import Goal, GoalEngine
from wizard_kernel.session import events as event_bus
from wizard_kernel.session.budget import BudgetManager
from wizard_kernel.session.investigation import Investigation


# ── Fixtures / builders ─────────────────────────────────────────────────────────

def _state():
    inv = Investigation(id="inv_ctx", repository_path=".", intent="understand architecture",
                        targets=["architecture"], options={})
    node = InvestigationNode(
        id="n1", type="read",
        action={"tool": "read_file", "params": {"path": "README.md"}},
        hypothesis=Hypothesis(kind=HypothesisKind.always_success), goal_id="g1",
    )
    goals = GoalEngine("inv_ctx")
    goals.add(Goal(id="g1", name="Map architecture", required_claim_types=["FRAMEWORK"]))
    kg = KnowledgeGraph("inv_ctx")
    budget = BudgetManager(40)
    return inv, node, goals, kg, budget


class _ObsStub:
    def __init__(self, observations=None):
        self._obs = observations or []

    def all(self):
        return self._obs


def _obs(obs_type, tool, payload):
    return Observation(id=f"obs_{tool}", investigation_id="inv_ctx", node_id="n1",
                       source_tool=tool, obs_type=obs_type, payload=payload,
                       created_at=datetime.now(timezone.utc))


def _sec(sec_id, priority, cost=10):
    return ContextSection(id=sec_id, priority=priority, scope="explorer_only",
                          content="body", token_cost=cost)


# ── sections.py ───────────────────────────────────────────────────────────────

def test_estimate_tokens_is_length_heuristic():
    assert estimate_tokens("") == 1                # never zero
    assert estimate_tokens("a" * 40) == 10         # ~4 chars/token


def test_section_autocomputes_token_cost():
    s = ContextSection(id="x", priority=1, scope="all_agents", content="abcd" * 10)
    assert s.token_cost == 10                       # 40 chars / 4


# ── packager.py ─────────────────────────────────────────────────────────────────

def test_packet_is_the_trust_stripped_contract():
    inv, node, goals, kg, budget = _state()
    packet = Packager().build_explorer_packet(inv, node, goals, kg, budget)
    # Exact key set the agents consume — no more (invariant 3).
    assert set(packet) == {
        "investigation_id", "intent", "targets", "current_node",
        "active_goals", "kg_summary", "remaining_budget",
    }
    assert packet["current_node"] == {"id": "n1", "type": "read",
                                      "action": node.action, "goal_id": "g1"}
    assert packet["remaining_budget"] == 40
    # No trust scores or raw relationships leak into the packet.
    assert "trust" not in packet and "relationships" not in packet


def test_explorer_sections_ids_and_priorities():
    inv, node, goals, kg, budget = _state()
    sections = Packager().build_explorer_sections(inv, node, goals, kg, budget, _ObsStub())
    assert [s.id for s in sections] == [
        "system_instructions", "available_tools", "repository_summary",
        "verified_claims", "unverified_assumptions", "recent_observations",
        "recent_failures", "budget_status",
    ]
    assert {s.id: s.priority for s in sections} == {
        "system_instructions": 100, "available_tools": 90, "repository_summary": 80,
        "verified_claims": 75, "unverified_assumptions": 70, "recent_observations": 60,
        "recent_failures": 50, "budget_status": 40,
    }
    assert all(s.token_cost > 0 for s in sections)


def test_available_tools_section_reuses_registry():
    from wizard_kernel.world.tools import _REGISTERED_TOOLS
    inv, node, goals, kg, budget = _state()
    tools_section = next(
        s for s in Packager().build_explorer_sections(inv, node, goals, kg, budget, _ObsStub())
        if s.id == "available_tools"
    )
    for tool in _REGISTERED_TOOLS:
        assert tool in tools_section.content


def test_sections_compress_observations_without_leaking_internals():
    pk = Packager()
    obs = [
        _obs("file_content", "read_file", {"ok": True, "content": "SECRET-PAYLOAD-BYTES"}),
        _obs("command_result", "execute_command",
             {"ok": False, "exit_code": 127, "stdout": "noise", "error": "cmd not found"}),
    ]
    recent = pk._recent_observations(obs)
    failures = pk._recent_failures(obs)
    # Compressed one-liners only.
    assert "file_content via read_file: ok=True" in recent
    assert "command_result via execute_command: ok=False exit=127" in recent
    assert "FAILED: execute_command" in failures
    # Raw payload internals must never appear (invariant 3 / "summaries" rule).
    assert "SECRET-PAYLOAD-BYTES" not in recent
    assert "noise" not in failures


def test_verified_vs_unverified_bucketing_hides_trust_scores():
    class _FakeClaim:
        def __init__(self, t, k, v, cid):
            self.claim_type, self.key, self.value, self.id = t, k, v, cid

    class _FakeKG:
        def summary(self):
            return {"claims_count": 2,
                    "high_trust_claims": [{"type": "FRAMEWORK", "key": "web", "value": "fastapi"}],
                    "contradictions": []}

        def all_claims(self):
            return [_FakeClaim("FRAMEWORK", "web", "fastapi", "c1"),
                    _FakeClaim("RUNTIME", "py", "3.12", "c2")]

        def trust_of(self, cid):
            return 0.9 if cid == "c1" else 0.3   # c2 below threshold => assumption

    pk = Packager()
    verified = pk._verified_claims(_FakeKG().summary())
    assumptions = pk._unverified_assumptions(_FakeKG())
    assert "VERIFIED: FRAMEWORK:web = fastapi" in verified
    assert "? RUNTIME:py = 3.12" in assumptions
    # The raw trust floats are kernel-side only — never rendered to the agent.
    assert "0.9" not in verified and "0.3" not in assumptions


# ── budget.py (token budget + KV cache) ─────────────────────────────────────────

def _explorer_section_set():
    return [_sec("budget_status", 40), _sec("recent_observations", 60), _sec("verified_claims", 75),
            _sec("system_instructions", 100), _sec("available_tools", 90), _sec("repository_summary", 80),
            _sec("unverified_assumptions", 70), _sec("recent_failures", 50)]


def test_kv_order_is_stable_then_growing_then_volatile():
    ordered = TokenBudget(max_context_tokens=100_000).optimize_and_fit(_explorer_section_set())
    assert [s.id for s in ordered] == [
        "system_instructions", "available_tools", "repository_summary",  # stable
        "verified_claims",                                               # growing
        "unverified_assumptions", "recent_observations", "recent_failures", "budget_status",  # volatile
    ]


def test_unknown_section_is_preserved_last_not_dropped():
    ordered = TokenBudget(max_context_tokens=100_000).optimize_and_fit(
        _explorer_section_set() + [_sec("mystery", 5)]
    )
    assert ordered[-1].id == "mystery"


def test_progressive_trim_drops_lowest_priority_first():
    # available == 40 tokens; 8 sections * 10 tokens => keep the top 4 by priority.
    tb = TokenBudget(max_context_tokens=40, reserved_output_fraction=0.0)
    kept = tb.optimize_and_fit(_explorer_section_set())
    assert [s.id for s in kept] == [
        "system_instructions", "available_tools", "repository_summary", "verified_claims",
    ]


def test_available_reserves_output_fraction():
    assert TokenBudget().available() == int(8192 * 0.85)


# ── cache.py ─────────────────────────────────────────────────────────────────────

def test_cache_hit_miss_and_invalidate():
    c = ContextCache()
    c.set("explorer", "n1", [_sec("system_instructions", 100)])
    assert c.get("explorer", "n1") is not None
    assert c.get("explorer", "n2") is None            # different node
    assert c.get("verifier", "n1") is None            # agent_type part of key
    version_before = c.state_version
    c.invalidate()
    assert c.state_version == version_before + 1
    assert c.get("explorer", "n1") is None            # cleared by version bump


def test_cache_is_bounded():
    c = ContextCache(max_size=3)
    for i in range(5):
        c.set("explorer", f"node{i}", [_sec("x", 1)])
    assert c.get("explorer", "node0") is None          # oldest evicted
    assert c.get("explorer", "node4") is not None       # newest kept


# ── audit.py ─────────────────────────────────────────────────────────────────────

def test_audit_emits_compact_context_supplied():
    bus = event_bus.create("inv_audit")
    ContextAudit(bus).record("explorer", "n1",
                             [_sec("system_instructions", 100), _sec("budget_status", 40)])
    supplied = [e for e in bus.get_recent_events() if e.event_type == CONTEXT_SUPPLIED]
    assert len(supplied) == 1
    payload = supplied[0].payload
    assert payload["agent_type"] == "explorer"
    assert payload["section_ids"] == ["system_instructions", "budget_status"]
    assert payload["token_total"] > 0
    assert "content" not in payload and "body" not in str(payload)   # compact


# ── engine.py (orchestrator) ──────────────────────────────────────────────────────

def test_engine_builds_packet_and_kv_ordered_sections():
    inv, node, goals, kg, budget = _state()
    eng = ContextEngine(event_bus.create("inv_eng"))
    result = eng.build_context("explorer", inv, node, goals, kg, budget, _ObsStub())
    assert result.from_cache is False and result.rejected is False
    # Packet matches the standalone packager (the agent contract).
    assert result.packet == Packager().build_explorer_packet(inv, node, goals, kg, budget)
    assert result.sections[0].id == "system_instructions"
    assert result.sections[-1].id == "budget_status"


def test_engine_cache_hit_then_invalidate():
    inv, node, goals, kg, budget = _state()
    eng = ContextEngine(event_bus.create("inv_eng2"))
    eng.build_context("explorer", inv, node, goals, kg, budget, _ObsStub())
    assert eng.build_context("explorer", inv, node, goals, kg, budget, _ObsStub()).from_cache is True
    eng.on_state_mutation()
    assert eng.build_context("explorer", inv, node, goals, kg, budget, _ObsStub()).from_cache is False


def test_engine_interceptor_reject():
    inv, node, goals, kg, budget = _state()

    def deny(sections, node, agent_type):
        return InterceptResult(action="reject", reason="policy: denied")

    eng = ContextEngine(event_bus.create("inv_eng3"), interceptor=Interceptor([deny]))
    result = eng.build_context("explorer", inv, node, goals, kg, budget, _ObsStub())
    assert result.rejected is True and result.reason == "policy: denied"
    assert result.sections == []
    assert result.packet["investigation_id"] == "inv_ctx"    # contract still built


def test_engine_interceptor_rewrite():
    inv, node, goals, kg, budget = _state()

    def keep_only_system(sections, node, agent_type):
        return InterceptResult(action="rewrite",
                               sections=[s for s in sections if s.id == "system_instructions"])

    eng = ContextEngine(event_bus.create("inv_eng4"), interceptor=Interceptor([keep_only_system]))
    result = eng.build_context("explorer", inv, node, goals, kg, budget, _ObsStub())
    assert [s.id for s in result.sections] == ["system_instructions"]
    assert result.rejected is False


def test_engine_unbuilt_agent_type_raises_explicit_seam():
    inv, node, goals, kg, budget = _state()
    eng = ContextEngine(event_bus.create("inv_eng5"))
    with pytest.raises(NotImplementedError):
        eng.build_context("verifier", inv, node, goals, kg, budget, _ObsStub())


# ── End-to-end: the real loop drives the engine ──────────────────────────────────

def test_loop_emits_context_supplied_end_to_end():
    from wizard_kernel.contracts.request import InvestigationRequest
    from wizard_kernel.contracts.status import LifecycleState
    from wizard_kernel.control import loop as kernel_loop
    from wizard_kernel.ports.planner import MockPlanner
    from wizard_kernel.session.manager import InvestigationManager

    manager = InvestigationManager()
    # `investigate architecture`, not `verify runtime`: this test is about the
    # Context Engine being driven, so it needs a run that reaches its nodes. The
    # older request completed only because the built-in planner ignored the
    # target and planned a read-only goal instead — the run reported success for
    # a question it had answered differently.
    req = InvestigationRequest(repository_path="/tmp", intent="investigate", targets=[],
                               options={"budget": 5, "sandbox_mode": "local_dev"})
    inv = manager.create(req)
    kernel_loop.run(inv, manager, MockPlanner())
    assert manager.get(inv.id).state == LifecycleState.completed

    events = event_bus.get_recent_events(0, inv.id)
    supplied = [e for e in events if e.event_type == CONTEXT_SUPPLIED]
    assert supplied, "loop must drive the Context Engine and audit each supply"
    # Every supply carries the explorer's stable system_instructions section.
    assert all("system_instructions" in e.payload["section_ids"] for e in supplied)
    assert any(e.payload["from_cache"] is False for e in supplied)
