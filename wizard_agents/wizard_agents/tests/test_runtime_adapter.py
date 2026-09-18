"""Runtime adapter routes — the seam the Python kernel's agent ports call.

The kernel POSTs its own packet shapes to these endpoints and validates the reply
against its own contracts (contracts/agent.py). These tests assert the adapter
speaks that wire format: the right keys, in the right shapes, with the kernel's
tool names — not the Agent System's internal ones.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# A packet shaped exactly like ContextPackager.build_explorer_packet emits.
def _kernel_explorer_packet(**overrides):
    packet = {
        "investigation_id": "inv_abc123",
        "intent": "investigate",
        "targets": [],
        "current_node": {
            "id": "node_read1",
            "type": "read",
            "action": {"tool": "read_file", "params": {"path": "package.json"}},
            "goal_id": "goal_0",
        },
        "active_goals": [{"id": "goal_0", "name": "Verify Runtime", "state": "open"}],
        "kg_summary": {"claims_count": 0, "high_trust_claims": [], "contradictions": []},
        "remaining_budget": 12,
    }
    packet.update(overrides)
    return packet


def _kernel_claims_packet(**overrides):
    packet = {
        "investigation_id": "inv_abc123",
        "claims": [
            {
                "claim_id": "cl_exec",
                "type": "RUNTIME",
                "key": "python --version",
                "value": "verified",
                "evidence": [
                    {"evidence_id": "ev1", "source_tier": "execution",
                     "support_type": "support"}
                ],
            },
            {
                "claim_id": "cl_doc",
                "type": "PACKAGE",
                "key": "name",
                "value": "wizard",
                "evidence": [
                    {"evidence_id": "ev2", "source_tier": "config_parse",
                     "support_type": "support"}
                ],
            },
        ],
    }
    packet.update(overrides)
    return packet


# ── Explorer ──────────────────────────────────────────────────────────────────

def test_explorer_returns_the_kernels_response_shape(client):
    r = client.post("/agent/explorer", json=_kernel_explorer_packet())
    assert r.status_code == 200, r.text
    body = r.json()

    # contracts/agent.py::ExplorerResponse — exactly these keys, no more.
    assert set(body) == {"investigation_id", "tool_request"}
    assert body["investigation_id"] == "inv_abc123"
    assert set(body["tool_request"]) == {"tool", "parameters", "reason"}
    assert body["tool_request"]["reason"]


def test_explorer_honours_the_nodes_planned_action(client):
    """The Planner said read package.json — that must survive the round trip."""
    body = client.post("/agent/explorer", json=_kernel_explorer_packet()).json()
    assert body["tool_request"]["tool"] == "read_file"
    assert body["tool_request"]["parameters"]["path"] == "package.json"


def test_explorer_folds_a_command_into_parameters(client):
    """The kernel carries the whole invocation in parameters; we split it out."""
    packet = _kernel_explorer_packet()
    packet["current_node"]["action"] = {
        "tool": "execute_command",
        "params": {"command": "python --version", "timeout_sec": 30},
    }
    body = client.post("/agent/explorer", json=packet).json()
    assert body["tool_request"]["tool"] == "execute_command"
    assert body["tool_request"]["parameters"]["command"] == "python --version"


def test_explorer_only_ever_proposes_kernel_executable_tools(client):
    """Whatever we return must be a tool the Runtime recognises.

    The kernel validates requests against its own registry and rejects anything
    else, so a proposal naming our internal vocabulary would be dead on arrival.
    """
    from wizard_kernel.control.tool_validator import _ALLOWED_TOOLS

    for action in (
        {"tool": "read_file", "params": {"path": "a.txt"}},
        {"tool": "list_tree", "params": {}},
        {"tool": "search_files", "params": {"pattern": "x", "glob": "**/*"}},
        {"tool": "execute_command", "params": {"command": "true"}},
        {"tool": "path_exists", "params": {"path": "a"}},
    ):
        packet = _kernel_explorer_packet()
        packet["current_node"]["action"] = action
        body = client.post("/agent/explorer", json=packet).json()
        assert body["tool_request"]["tool"] in _ALLOWED_TOOLS, action


def test_explorer_resolves_the_goal_name_from_active_goals(client):
    """The packet names the goal by id only; we must not emit a blank goal."""
    packet = _kernel_explorer_packet()
    packet["active_goals"] = [{"id": "goal_0", "name": "Verify Containerization",
                               "state": "open"}]
    body = client.post("/agent/explorer", json=packet).json()
    assert "Verify Containerization" in body["tool_request"]["reason"]


@pytest.mark.parametrize("packet", [
    {"investigation_id": "inv_x", "current_node": {"id": "", "goal": ""}},
    {"investigation_id": "inv_x", "current_node": {}},
    {"current_node": {"id": "node_1"}},
    {"investigation_id": "inv_x", "current_node": {"id": "   "}},
])
def test_explorer_rejects_an_unusable_packet(client, packet):
    """A malformed packet must fail loudly — never be patched up with a placeholder."""
    assert client.post("/agent/explorer", json=packet).status_code == 422


def test_verifier_rejects_a_packet_with_no_investigation_id(client):
    r = client.post("/agent/verifier", json={"claims": _kernel_claims_packet()["claims"]})
    assert r.status_code == 422


# ── Verifier ──────────────────────────────────────────────────────────────────

def test_verifier_returns_the_kernels_assessment_shape(client):
    r = client.post("/agent/verifier", json=_kernel_claims_packet())
    assert r.status_code == 200, r.text
    body = r.json()

    # contracts/agent.py::VerifierAssessment — exactly these keys.
    assert set(body) == {"investigation_id", "assessment", "weak_claims",
                         "recommended_additional_investigations"}
    assert body["investigation_id"] == "inv_abc123"
    assert body["assessment"] in ("overall_sufficient", "needs_more_work")


def test_verifier_uses_evidence_provenance_to_judge_claims(client):
    """An execution-backed claim is not weak; a config-parse-only one is."""
    body = client.post("/agent/verifier", json=_kernel_claims_packet()).json()
    assert "cl_exec" not in body["weak_claims"]
    assert "cl_doc" in body["weak_claims"]


def test_verifier_asks_for_more_work_only_when_it_found_something(client):
    body = client.post("/agent/verifier", json=_kernel_claims_packet()).json()
    assert body["assessment"] == "needs_more_work"
    assert body["recommended_additional_investigations"]

    # Every claim backed by execution evidence → nothing left to recommend.
    packet = _kernel_claims_packet()
    packet["claims"] = [packet["claims"][0]]
    body = client.post("/agent/verifier", json=packet).json()
    assert body["assessment"] == "overall_sufficient"
    assert body["recommended_additional_investigations"] == []


def test_verifier_never_leaks_a_trust_score(client):
    """Invariant 3: the assessment carries verdicts, never trust numbers."""
    body = client.post("/agent/verifier", json=_kernel_claims_packet()).json()
    assert "trust" not in body
    assert all(isinstance(c, str) for c in body["weak_claims"])
