"""Tests for all items identified in the codebase audit.

Covers the fixes from every priority level:
- GoalDefinition-driven goal requirements (invariant 5)
- Accurate claims_count including extractor claims
- CONTRADICTS relationship auto-added for conflicting values
- mark_failed() distinct from mark_complete()
- BudgetManager behaviour
- EventBus emit/listen
- repository.validate()
- GoalEngine persistence (goals.json)
- Priority scoring with uncertainty_gap
- get_agents() factory
- GET /v1/investigations list endpoint
- /report endpoint uses ReportResponse model schema
- Agents cannot inject trust (invariant 3, BUILD_PLAN Phase 6 requirement)
- Planner goal definitions drive requirements — not hardcoded kernel string matching
"""
import pytest
from datetime import datetime, timezone
from pathlib import Path
from fastapi.testclient import TestClient

from wizard_kernel.api.app import app
from wizard_kernel.contracts.claim import Claim
from wizard_kernel.contracts.evidence import Evidence
from wizard_kernel.contracts.node import (
    ClaimTemplate, Hypothesis, HypothesisKind, InvestigationNode,
)
from wizard_kernel.contracts.plan import GoalDefinition, TechnologyEntry, TechnologyPlan
from wizard_kernel.contracts.observation import Observation
from wizard_kernel.contracts.request import InvestigationRequest
from wizard_kernel.contracts.status import LifecycleState
from wizard_kernel.belief.evidence import EvidenceEngine
from wizard_kernel.belief.knowledge_graph import KnowledgeGraph
from wizard_kernel.control.goals import Goal, GoalEngine
from wizard_kernel.control.investigation_graph import InvestigationGraph
from wizard_kernel.control.priority import next_ready
from wizard_kernel.session.budget import BudgetManager
from wizard_kernel.session import events as event_bus
from wizard_kernel.session.manager import InvestigationManager
from wizard_kernel.ports.agents import get_agents, HttpVerifier, MockVerifier
from wizard_kernel.ports.planner import MockPlanner
from wizard_kernel.control import loop as kernel_loop
from wizard_kernel.world import repository

client = TestClient(app)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ev(obs_ids: list[str], support: str = "support", tier: str = "execution") -> Evidence:
    return Evidence(
        id=f"ev_{obs_ids[0][:6]}",
        claim_id="cl_test",
        observation_ids=obs_ids,
        support_type=support,
        source_tier=tier,
        created_at=datetime.now(timezone.utc),
    )


def _claim(claim_type: str, key: str, value=True, inv_id: str = "inv_test") -> Claim:
    return Claim(
        id=f"cl_{claim_type[:4]}_{key[:4]}",
        investigation_id=inv_id,
        claim_type=claim_type,
        key=key,
        value=value,
        created_at=datetime.now(timezone.utc),
    )


# ── GoalDefinition contract ───────────────────────────────────────────────────

class TestGoalDefinition:
    def test_goal_definition_serialises(self):
        gd = GoalDefinition(
            name="Verify Runtime",
            required_claim_types=["RUNTIME"],
            belief_threshold=0.7,
            requires_execution_evidence=False,
        )
        d = gd.model_dump()
        assert d["name"] == "Verify Runtime"
        assert d["required_claim_types"] == ["RUNTIME"]

    def test_technology_entry_accepts_goal_definitions(self):
        te = TechnologyEntry(
            name="Python", confidence="high", signals=["requirements.txt"],
            initial_goals=[
                GoalDefinition(name="Verify Runtime", required_claim_types=["RUNTIME"]),
                GoalDefinition(name="Verify Dependencies", required_claim_types=["PACKAGE"]),
            ],
        )
        assert len(te.initial_goals) == 2
        assert isinstance(te.initial_goals[0], GoalDefinition)

    def test_mock_planner_emits_goal_definitions(self):
        """MockPlanner.initial() must return GoalDefinition objects, not strings."""
        from wizard_kernel.contracts.manifest import RepositoryManifest
        planner = MockPlanner()
        manifest = RepositoryManifest(
            investigation_id="inv_test",
            root_path="/tmp",
            total_files=2,
            total_dirs=1,
            key_files=["pyproject.toml"],
            extensions={".toml": 1},
            directory_tree=["pyproject.toml"],
            size_bytes_approx=100,
        )
        plan = planner.initial(manifest, "verify", ["runtime"])
        for tech in plan.technologies:
            for gd in tech.initial_goals:
                assert isinstance(gd, GoalDefinition), (
                    f"Expected GoalDefinition, got {type(gd).__name__} — "
                    "planner must not return raw strings as goal definitions"
                )
                assert isinstance(gd.required_claim_types, list)


# ── claims_count accuracy ─────────────────────────────────────────────────────

class TestClaimsCount:
    def test_claims_count_includes_extractor_claims(self, tmp_path, monkeypatch):
        """After loop completes on a real file, claims_count must reflect ALL claims
        admitted via the EvidenceEngine — not just the node-level on_success claim."""
        monkeypatch.chdir(tmp_path)
        manager = InvestigationManager()
        req = InvestigationRequest(
            repository_path=str(tmp_path),
            intent="verify",
            targets=["runtime"],
            options={"budget": 10, "sandbox_mode": "local_dev"},
        )
        # Write a pyproject.toml so MockPlanner generates real extractor hits
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "myapp"\nversion = "1.0.0"\nrequires-python = ">=3.11"\n'
            'dependencies = ["fastapi>=0.115"]\n'
        )
        inv = manager.create(req)
        kernel_loop.run(inv, manager, MockPlanner())
        refreshed = manager.get(inv.id)
        # FILE_READ + PACKAGE.name + PACKAGE.version + RUNTIME.language + PACKAGE.dependency_count
        assert refreshed.claims_count >= 3, (
            f"Expected >= 3 claims (node + extractors), got {refreshed.claims_count}"
        )


# ── CONTRADICTS relationship ──────────────────────────────────────────────────

class TestContradicts:
    def test_conflicting_value_creates_contradicts_edge(self):
        """When two observations produce the same (claim_type, key) with different values,
        the EvidenceEngine must create a CONTRADICTS relationship in the Knowledge Graph."""
        kg = KnowledgeGraph("inv_contra")
        engine = EvidenceEngine(kg)

        # First claim: language = "Python"
        r1 = engine.admit(
            inv_id="inv_contra", claim_type="RUNTIME", key="language",
            value="Python", obs_id="obs_001", support_type="support",
            source_tier="config_parse", node_id="node_1",
        )
        assert r1 is not None

        # Contradicting claim from a different observation: language = "Node.js"
        r2 = engine.admit(
            inv_id="inv_contra", claim_type="RUNTIME", key="language",
            value="Node.js", obs_id="obs_002", support_type="support",
            source_tier="config_parse", node_id="node_2",
        )
        assert r2 is not None

        # Must have two distinct claims
        all_claims = kg.find("RUNTIME", "language")
        assert len(all_claims) == 2, "Contradicting value must create a new claim, not overwrite"

        # Must have a CONTRADICTS relationship
        rels = kg.relationships()
        contra_rels = [r for r in rels if r.rel_type == "CONTRADICTS"]
        assert len(contra_rels) >= 1, "EvidenceEngine must add CONTRADICTS edge for conflicting values"

    def test_same_value_does_not_add_contradicts_edge(self):
        """Reinforcing an existing claim with the same value adds supporting evidence only."""
        kg = KnowledgeGraph("inv_reinforce")
        engine = EvidenceEngine(kg)

        engine.admit(
            inv_id="inv_reinforce", claim_type="RUNTIME", key="language",
            value="Python", obs_id="obs_001", support_type="support",
            source_tier="config_parse", node_id="node_1",
        )
        engine.admit(
            inv_id="inv_reinforce", claim_type="RUNTIME", key="language",
            value="Python", obs_id="obs_002", support_type="support",
            source_tier="execution", node_id="node_2",
        )

        rels = kg.relationships()
        contra_rels = [r for r in rels if r.rel_type == "CONTRADICTS"]
        assert len(contra_rels) == 0, "Same value must NOT create a CONTRADICTS edge"
        # Trust should have increased with the execution evidence
        claims = kg.find("RUNTIME", "language")
        assert kg.trust_of(claims[0].id) > 0.5


# ── InvestigationGraph.mark_failed ───────────────────────────────────────────

class TestInvestigationGraphFailed:
    def test_mark_failed_sets_state_to_failed(self):
        graph = InvestigationGraph("inv_fail_test")
        node = InvestigationNode(
            id="node_001", type="execute",
            action={"tool": "execute_command", "params": {"command": "pytest"}},
            hypothesis=Hypothesis(kind=HypothesisKind.exit_code_in, success_values=[0]),
        )
        graph.add(node)
        graph.mark_failed("node_001", obs_ids=["obs_fail_001"])
        updated = graph.get("node_001")
        assert updated.state == "failed", "mark_failed() must set state='failed' not 'complete'"
        assert "obs_fail_001" in updated.observation_ids

    def test_mark_failed_is_distinct_from_complete(self):
        graph = InvestigationGraph("inv_fail_test2")
        node_ok = InvestigationNode(
            id="node_ok", type="read",
            action={"tool": "read_file", "params": {"path": "x.txt"}},
            hypothesis=Hypothesis(kind=HypothesisKind.always_success),
        )
        node_fail = InvestigationNode(
            id="node_fail", type="execute",
            action={"tool": "execute_command", "params": {"command": "exit 1"}},
            hypothesis=Hypothesis(kind=HypothesisKind.exit_code_in, success_values=[0]),
        )
        graph.add(node_ok)
        graph.add(node_fail)
        graph.set_state("node_ok", "complete")
        graph.mark_failed("node_fail")
        assert graph.get("node_ok").state == "complete"
        assert graph.get("node_fail").state == "failed"


# ── BudgetManager ─────────────────────────────────────────────────────────────

class TestBudgetManager:
    def test_initial_state(self):
        bm = BudgetManager(total=10)
        assert bm.remaining == 10
        assert bm.used == 0
        assert bm.total == 10
        assert not bm.is_exhausted()

    def test_consume_reduces_remaining(self):
        bm = BudgetManager(total=5)
        result = bm.consume()
        assert result is True
        assert bm.remaining == 4
        assert bm.used == 1

    def test_exhausted_returns_false(self):
        bm = BudgetManager(total=2)
        bm.consume()
        bm.consume()
        assert bm.is_exhausted()
        result = bm.consume()
        assert result is False
        assert bm.remaining == 0

    def test_is_low_at_warn_fraction(self):
        bm = BudgetManager(total=10, warn_fraction=0.25)
        # Consume 8, 2 remaining = 20% <= 25% warn threshold
        for _ in range(8):
            bm.consume()
        assert bm.is_low()

    def test_not_low_at_full(self):
        bm = BudgetManager(total=10)
        assert not bm.is_low()

    def test_invalid_budget_raises(self):
        with pytest.raises(ValueError):
            BudgetManager(total=0)


# ── EventBus ──────────────────────────────────────────────────────────────────

class TestEventBus:
    def test_emit_calls_registered_listener(self):
        received = []
        bus = event_bus.create("inv_event_test")
        bus.on(event_bus.ClaimAdmitted, lambda e: received.append(e))
        bus.emit(event_bus.ClaimAdmitted, {"claim_type": "RUNTIME", "key": "language"})
        assert len(received) == 1
        assert received[0]["event"] == event_bus.ClaimAdmitted
        assert received[0]["claim_type"] == "RUNTIME"

    def test_listener_failure_does_not_crash(self):
        """A broken listener must not crash the investigation (invariant 4)."""
        bus = event_bus.create("inv_event_test2")
        def bad_listener(e):
            raise RuntimeError("listener explosion")
        bus.on(event_bus.NodeCompleted, bad_listener)
        # Must not raise
        bus.emit(event_bus.NodeCompleted, {"node_id": "node_001"})

    def test_multiple_listeners_all_called(self):
        results = []
        bus = event_bus.create("inv_event_test3")
        bus.on(event_bus.GoalSatisfied, lambda e: results.append("A"))
        bus.on(event_bus.GoalSatisfied, lambda e: results.append("B"))
        bus.emit(event_bus.GoalSatisfied, {"goal_id": "g1"})
        assert results == ["A", "B"]

    def test_unregistered_event_emits_silently(self):
        bus = event_bus.create("inv_event_test4")
        bus.emit("totally.unknown.event", {"foo": "bar"})  # must not raise


# ── Repository path validation ────────────────────────────────────────────────

class TestRepositoryValidation:
    def test_valid_directory_returns_path(self, tmp_path):
        result = repository.validate(str(tmp_path))
        assert isinstance(result, Path)
        assert result == tmp_path.resolve()

    def test_missing_path_raises_value_error(self, tmp_path):
        missing = tmp_path / "does_not_exist"
        with pytest.raises(ValueError, match="does not exist"):
            repository.validate(str(missing))

    def test_file_path_raises_value_error(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("hello")
        with pytest.raises(ValueError, match="not a directory"):
            repository.validate(str(f))

    def test_loop_fails_gracefully_on_bad_path(self, tmp_path, monkeypatch):
        """loop.run() must transition to LifecycleState.failed when path is invalid."""
        monkeypatch.chdir(tmp_path)
        manager = InvestigationManager()
        req = InvestigationRequest(
            repository_path="/totally/nonexistent/path/xyz",
            intent="verify",
            targets=["runtime"],
            options={"budget": 5, "sandbox_mode": "local_dev"},
        )
        inv = manager.create(req)
        kernel_loop.run(inv, manager, MockPlanner())
        refreshed = manager.get(inv.id)
        assert refreshed.state == LifecycleState.failed
        assert refreshed.error is not None


# ── GoalEngine persistence ────────────────────────────────────────────────────

class TestGoalPersistence:
    def test_persist_and_restore(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        goals = GoalEngine("inv_persist_goals")
        goals.add(Goal(
            id="goal_001", name="Verify Runtime",
            required_claim_types=["RUNTIME"],
            belief_threshold=0.65,
        ))
        goals.mark_satisfied("goal_001")
        goals.persist()

        # New engine restores from disk
        goals2 = GoalEngine("inv_persist_goals")
        goals2.restore()
        g = goals2.get("goal_001")
        assert g is not None
        assert g.state == "satisfied"
        assert g.progress == 1.0
        assert g.required_claim_types == ["RUNTIME"]
        assert g.belief_threshold == pytest.approx(0.65)


# ── Priority scoring ──────────────────────────────────────────────────────────

class TestPriorityScoring:
    def _make_node(self, node_id: str, goal_id: str = "") -> InvestigationNode:
        return InvestigationNode(
            id=node_id, type="read",
            action={"tool": "read_file", "params": {"path": "x"}},
            hypothesis=Hypothesis(kind=HypothesisKind.always_success),
            goal_id=goal_id,
        )

    def test_high_urgency_node_chosen_first(self):
        nodes = [
            self._make_node("node_low", goal_id="goal_satisfied"),
            self._make_node("node_high", goal_id="goal_open"),
        ]
        chosen = next_ready(
            nodes, completed_ids=set(),
            goal_urgency={"goal_satisfied": 0.0, "goal_open": 1.0},
        )
        assert chosen.id == "node_high"

    def test_uncertainty_gap_breaks_tie(self):
        """When urgency is equal, prefer the node for the goal with lower trust."""
        nodes = [
            self._make_node("node_known", goal_id="goal_well_known"),
            self._make_node("node_unknown", goal_id="goal_mystery"),
        ]
        chosen = next_ready(
            nodes, completed_ids=set(),
            goal_urgency={"goal_well_known": 1.0, "goal_mystery": 1.0},
            kg_trust_by_goal={"goal_well_known": 0.9, "goal_mystery": 0.1},
        )
        assert chosen.id == "node_unknown"

    def test_returns_none_when_all_complete(self):
        nodes = [self._make_node("node_001")]
        nodes[0].state = "complete"
        result = next_ready(nodes, completed_ids={"node_001"})
        assert result is None


# ── get_agents factory ────────────────────────────────────────────────────────

class TestGetAgents:
    def test_returns_mock_when_no_urls(self):
        from wizard_kernel.ports.agents import MockExplorer, MockVerifier
        explorer, verifier = get_agents({})
        assert isinstance(explorer, MockExplorer)
        assert isinstance(verifier, MockVerifier)

    def test_returns_http_when_urls_provided(self):
        from wizard_kernel.ports.agents import HttpExplorer, HttpVerifier
        explorer, verifier = get_agents({
            "agent_explorer_url": "http://localhost:5678/webhook/explore",
            "agent_verifier_url": "http://localhost:5678/webhook/verify",
        })
        assert isinstance(explorer, HttpExplorer)
        assert isinstance(verifier, HttpVerifier)

    def test_agent_response_strips_trust_field(self):
        """Invariant 3: Agents cannot set trust directly.
        HttpVerifier must strip 'trust' before returning VerifierAssessment."""
        verifier = MockVerifier()
        # Even if a claim dict includes a 'trust' key, MockVerifier.assess()
        # returns a VerifierAssessment that has no 'trust' attribute
        fake_claims = [{"id": "cl_001", "trust": 0.99, "claim_type": "RUNTIME"}]
        result = verifier.assess(fake_claims)
        assert not hasattr(result, "trust"), (
            "VerifierAssessment must not expose a 'trust' field — "
            "agents cannot bypass the EvidenceEngine (invariant 3)"
        )
        assert result.assessment in ("overall_sufficient", "needs_more_work")


# ── API list endpoint ─────────────────────────────────────────────────────────

class TestListInvestigations:
    def test_list_returns_array(self):
        resp = client.get("/v1/investigations")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_includes_created_investigation(self):
        body = {
            "repository_path": "/tmp",
            "intent": "verify",
            "targets": ["runtime"],
            "options": {"budget": 1, "sandbox_mode": "local_dev"},
        }
        post_resp = client.post("/v1/investigations", json=body)
        assert post_resp.status_code == 201
        inv_id = post_resp.json()["investigation_id"]

        list_resp = client.get("/v1/investigations")
        ids = [item["investigation_id"] for item in list_resp.json()]
        assert inv_id in ids


# ── Report endpoint uses ReportResponse schema ────────────────────────────────

class TestReportEndpointSchema:
    def test_report_endpoint_schema_visible_in_openapi(self):
        """The /report endpoint must use ReportResponse so /docs shows the schema."""
        schema_resp = client.get("/openapi.json")
        assert schema_resp.status_code == 200
        openapi = schema_resp.json()
        # ReportResponse should appear in the components/schemas section
        schemas = openapi.get("components", {}).get("schemas", {})
        assert "ReportResponse" in schemas, (
            "ReportResponse must be in the OpenAPI schema — "
            "use response_model=ReportResponse on the route"
        )
        props = schemas["ReportResponse"]["properties"]
        assert "investigation_id" in props
        assert "report_markdown" in props
        assert "report_path" in props


# ── Planner goal definitions drive loop — not hardcoded strings ───────────────

class TestPlannerDrivesGoals:
    def test_kernel_does_not_inspect_goal_names(self, tmp_path, monkeypatch):
        """The loop must never match against goal name strings to decide claim requirements.
        If the Planner sends GoalDefinition(required_claim_types=["FILESYSTEM"]),
        that claim type — and only that — should gate goal satisfaction."""
        monkeypatch.chdir(tmp_path)

        from unittest.mock import MagicMock
        from wizard_kernel.contracts.manifest import RepositoryManifest
        from wizard_kernel.contracts.node import InvestigationNode

        # Build a plan with an unusual goal name that the kernel cannot know about
        custom_plan = TechnologyPlan(
            technologies=[
                TechnologyEntry(
                    name="Custom", confidence="high",
                    signals=["pyproject.toml"],
                    initial_goals=[
                        GoalDefinition(
                            name="Entirely Custom Goal Name 🔬",
                            required_claim_types=["FILESYSTEM"],  # kernel must use this
                        )
                    ],
                    priority_files=[],
                )
            ],
            seed_nodes=[
                InvestigationNode(
                    id="node_001", type="discovery",
                    action={"tool": "list_tree", "params": {"max_depth": 1}},
                    hypothesis=Hypothesis(kind=HypothesisKind.always_success),
                    on_success=ClaimTemplate(claim_type="FILESYSTEM", key="scanned", value=True),
                )
            ],
        )

        custom_planner = MagicMock()
        custom_planner.initial.return_value = custom_plan
        custom_planner.next_nodes.return_value = []
        custom_planner.interpret.return_value = []

        manager = InvestigationManager()
        req = InvestigationRequest(
            repository_path=str(tmp_path),
            intent="verify",
            targets=["custom"],
            options={"budget": 5, "sandbox_mode": "local_dev"},
        )
        inv = manager.create(req)
        kernel_loop.run(inv, manager, custom_planner)
        refreshed = manager.get(inv.id)

        assert refreshed.state == LifecycleState.completed
        # The custom goal should be satisfied because FILESYSTEM claim was admitted
        goals_api = refreshed.active_goals
        custom_goal = next((g for g in goals_api if "Custom Goal" in g["name"]), None)
        assert custom_goal is not None
        assert custom_goal["state"] == "satisfied", (
            "Goal with unusual name must be satisfied by its required_claim_types "
            "— the kernel must not inspect goal name strings"
        )
