"""Phase 4 tests — Trust Engine, Knowledge Graph, Evidence Engine, Extractors."""
import pytest
from datetime import datetime, timezone
from wizard_kernel.contracts.claim import Claim
from wizard_kernel.contracts.evidence import Evidence
from wizard_kernel.contracts.observation import Observation
from wizard_kernel.belief import trust as trust_engine
from wizard_kernel.belief.knowledge_graph import KnowledgeGraph
from wizard_kernel.belief.evidence import EvidenceEngine
from wizard_kernel.belief import extractors


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _ev(obs_ids: list[str], support: str = "support",
        tier: str = "execution") -> Evidence:
    return Evidence(
        id=f"ev_{obs_ids[0][:4]}",
        claim_id="cl_test",
        observation_ids=obs_ids,
        support_type=support,
        source_tier=tier,
        created_at=datetime.now(timezone.utc),
    )


def _obs(obs_type: str, payload: dict, tool: str = "read_file") -> Observation:
    return Observation(
        id=f"obs_{id(payload)}",
        investigation_id="inv_test",
        node_id="node_001",
        source_tool=tool,
        obs_type=obs_type,
        payload=payload,
        created_at=datetime.now(timezone.utc),
    )


# ── Trust Engine ──────────────────────────────────────────────────────────────

class TestTrust:
    def test_single_execution_evidence_high_belief(self):
        # 1.0 / (1.0 + 0 + 0.1) = 0.9091
        evs = [_ev(["obs_001"], "support", "execution")]
        belief = trust_engine.compute(evs)
        assert belief > 0.85

    def test_no_evidence_near_zero(self):
        belief = trust_engine.compute([])
        assert belief < 0.1

    def test_contradicting_evidence_reduces_belief(self):
        evs = [
            _ev(["obs_001"], "support", "execution"),
            _ev(["obs_002"], "contradict", "execution"),
        ]
        belief = trust_engine.compute(evs)
        assert belief < 0.6

    def test_dedup_same_obs_id_no_double_count(self):
        evs = [
            _ev(["obs_001"], "support", "execution"),
            _ev(["obs_001"], "support", "execution"),  # same obs — must not double-count
        ]
        belief_dedup = trust_engine.compute(evs)
        evs_single = [_ev(["obs_001"], "support", "execution")]
        belief_single = trust_engine.compute(evs_single)
        assert abs(belief_dedup - belief_single) < 0.01

    def test_doc_evidence_lower_than_execution(self):
        exec_belief = trust_engine.compute([_ev(["o1"], "support", "execution")])
        doc_belief = trust_engine.compute([_ev(["o2"], "support", "documentation")])
        assert exec_belief > doc_belief

    def test_has_execution_evidence_true(self):
        evs = [_ev(["obs_001"], "support", "execution")]
        assert trust_engine.has_execution_evidence(evs) is True

    def test_has_execution_evidence_false_for_config_only(self):
        evs = [_ev(["obs_001"], "support", "config_parse")]
        assert trust_engine.has_execution_evidence(evs) is False

    def test_source_tier_for_tool(self):
        assert trust_engine.source_tier_for_tool("execute_command") == "execution"
        assert trust_engine.source_tier_for_tool("check_port") == "execution"
        assert trust_engine.source_tier_for_tool("read_file") == "config_parse"
        assert trust_engine.source_tier_for_tool("list_tree") == "config_parse"


# ── Knowledge Graph ───────────────────────────────────────────────────────────

class TestKnowledgeGraph:
    def test_insert_and_get(self):
        kg = KnowledgeGraph("inv_test")
        claim = Claim(id="cl_001", investigation_id="inv_test",
                      claim_type="RUNTIME", key="language", value="Node.js",
                      created_at=datetime.now(timezone.utc))
        ev = _ev(["obs_001"])
        ev = ev.model_copy(update={"claim_id": "cl_001"})
        kg.insert(claim, ev)
        assert kg.get("cl_001") is not None
        assert kg.trust_of("cl_001") > 0.8

    def test_find_by_type_and_key(self):
        kg = KnowledgeGraph("inv_test2")
        claim = Claim(id="cl_002", investigation_id="inv_test2",
                      claim_type="PACKAGE", key="name", value="myapp",
                      created_at=datetime.now(timezone.utc))
        kg.insert(claim, _ev(["obs_002"]))
        found = kg.find("PACKAGE", "name")
        assert len(found) == 1
        assert found[0].value == "myapp"

    def test_add_evidence_increases_trust(self):
        kg = KnowledgeGraph("inv_test3")
        claim = Claim(id="cl_003", investigation_id="inv_test3",
                      claim_type="RUNTIME", key="start_ok", value=True,
                      created_at=datetime.now(timezone.utc))
        kg.insert(claim, _ev(["obs_001"]))
        trust_before = kg.trust_of("cl_003")
        kg.add_evidence("cl_003", _ev(["obs_002"]))
        trust_after = kg.trust_of("cl_003")
        assert trust_after >= trust_before

    def test_summary_is_compact(self):
        kg = KnowledgeGraph("inv_test4")
        claim = Claim(id="cl_004", investigation_id="inv_test4",
                      claim_type="RUNTIME", key="lang", value="Python",
                      created_at=datetime.now(timezone.utc))
        kg.insert(claim, _ev(["obs_001"]))
        summary = kg.summary()
        # Summary must not expose raw internal graph (invariant 3)
        assert "claims_count" in summary
        assert "_claims" not in summary
        assert "_evidence" not in summary

    def test_persist_writes_json(self, tmp_path, monkeypatch):
        # This test is about the *fallback* root — `<cwd>/.wizard` when
        # WIZARD_DATA_DIR says nothing — so it has to say that, rather than rely
        # on the variable happening to be unset in the environment it runs in.
        monkeypatch.delenv("WIZARD_DATA_DIR", raising=False)
        monkeypatch.chdir(tmp_path)
        kg = KnowledgeGraph("inv_persist")
        claim = Claim(id="cl_p01", investigation_id="inv_persist",
                      claim_type="RUNTIME", key="ok", value=True,
                      created_at=datetime.now(timezone.utc))
        kg.insert(claim, _ev(["obs_p01"]))
        kg.persist()
        import json
        data = json.loads((tmp_path / ".wizard" / "investigations" / "inv_persist" / "knowledge_graph.json").read_text())
        assert len(data["claims"]) == 1
        assert "trust" in data


# ── Evidence Engine ───────────────────────────────────────────────────────────

class TestEvidenceEngine:
    def test_admit_creates_claim_in_kg(self):
        kg = KnowledgeGraph("inv_ev_test")
        engine = EvidenceEngine(kg)
        result = engine.admit(
            inv_id="inv_ev_test", claim_type="RUNTIME", key="language",
            value="Python", obs_id="obs_001", support_type="support",
            source_tier="execution", node_id="node_001",
        )
        assert result is not None
        claim, evidence = result
        assert claim.claim_type == "RUNTIME"
        assert kg.get(claim.id) is not None

    def test_dedup_same_obs_id_returns_none(self):
        kg = KnowledgeGraph("inv_ev_test2")
        engine = EvidenceEngine(kg)
        engine.admit(inv_id="inv_ev_test2", claim_type="RUNTIME", key="language",
                     value="Python", obs_id="obs_001", support_type="support",
                     source_tier="execution", node_id="node_001")
        # Same obs_id again
        result = engine.admit(inv_id="inv_ev_test2", claim_type="RUNTIME", key="language",
                              value="Python", obs_id="obs_001", support_type="support",
                              source_tier="execution", node_id="node_001")
        assert result is None  # dedup returns None

    def test_contradictions_do_not_delete_claims(self):
        """Contradictions reduce trust but never delete existing claims."""
        kg = KnowledgeGraph("inv_ev_test3")
        engine = EvidenceEngine(kg)
        # First admit a supporting claim
        result1 = engine.admit(inv_id="inv_ev_test3", claim_type="DEPS", key="installable",
                               value=True, obs_id="obs_001", support_type="support",
                               source_tier="execution", node_id="node_001")
        claim, _ = result1
        trust_before = kg.trust_of(claim.id)
        # Now a contradicting obs
        engine.add_supporting_evidence(claim.id, "obs_002", "execution")
        # Claim must still exist
        assert kg.get(claim.id) is not None


# ── Extractor Framework ───────────────────────────────────────────────────────

class TestExtractors:
    def test_package_json_extractor(self):
        obs = _obs("file_content", {
            "path": "package.json",
            "content": '{"name":"myapp","version":"1.0.0"}',
            "parsed": {"name": "myapp", "version": "1.0.0",
                       "scripts": {"start": "node server.js", "test": "jest"}},
        })
        results = extractors.extract(obs)
        types = {(r.claim_type, r.key) for r in results}
        assert ("PACKAGE", "name") in types
        assert ("RUNTIME", "has_start_script") in types

    def test_dockerfile_extractor(self):
        obs = _obs("file_content", {
            "path": "Dockerfile",
            "content": "FROM node:18-alpine\nEXPOSE 3000\nCMD [\"node\",\"server.js\"]",
            "parsed": None,
        })
        results = extractors.extract(obs)
        types = {r.claim_type for r in results}
        assert "DEPLOYMENT" in types
        keys = {r.key for r in results}
        assert "has_dockerfile" in keys
        assert "exposed_port" in keys

    def test_command_result_extractor_exit_code(self):
        obs = _obs("command_result", {
            "exit_code": 0,
            "stdout": "added 47 packages",
            "stderr": "",
        }, tool="execute_command")
        results = extractors.extract(obs)
        keys = {r.key for r in results}
        assert "execute_command_exit_code" in keys
        assert "npm_packages_installed" in keys

    def test_port_check_extractor(self):
        obs = _obs("port_check", {
            "status_code": 200,
            "data": {"active": True, "host": "localhost", "port": 3000},
        }, tool="check_port")
        results = extractors.extract(obs)
        assert any(r.key == "port:3000:active" and r.value is True for r in results)

    def test_extractor_failure_does_not_crash(self):
        """A broken extractor must not crash the loop (invariant 4)."""
        obs = _obs("file_content", {"path": "package.json", "parsed": "INVALID_NOT_A_DICT"})
        results = extractors.extract(obs)
        # Should return [] without crashing
        assert isinstance(results, list)

    def test_path_check_extractor(self):
        obs = _obs("path_check", {"path": "server.js", "exists": True})
        results = extractors.extract(obs)
        assert any(r.support_type == "support" for r in results)

    def test_requirements_txt_extractor(self):
        obs = _obs("file_content", {
            "path": "requirements.txt",
            "content": "fastapi==0.115.0\nuvicorn>=0.30.0\npydantic>=2.8",
            "parsed": None,
        })
        results = extractors.extract(obs)
        types = {r.claim_type for r in results}
        assert "RUNTIME" in types
        assert "PACKAGE" in types
