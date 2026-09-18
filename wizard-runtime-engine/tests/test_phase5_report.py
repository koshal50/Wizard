"""Phase 5 tests — Report generation, evidence traceability, API endpoint.

Tests mirror the BUILD_PLAN.md Phase 5 milestones exactly.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wizard_kernel.api.app import create_app
from wizard_kernel.belief.evidence import EvidenceEngine
from wizard_kernel.belief.knowledge_graph import KnowledgeGraph
from wizard_kernel.contracts.claim import Claim
from wizard_kernel.contracts.evidence import Evidence
from wizard_kernel.contracts.observation import Observation
from wizard_kernel.control import report as report_module
from wizard_kernel.control.goals import Goal, GoalEngine
from wizard_kernel.control.investigation_graph import InvestigationGraph
from wizard_kernel.session.investigation import Investigation


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _inv(tmp_path) -> Investigation:
    return Investigation(
        id="inv_phase5test",
        repository_path=str(tmp_path),
        intent="verify",
        targets=["runtime"],
        options={},
        budget_total=10,
        budget_remaining=3,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _obs(inv_id: str, node_id: str, tool: str = "execute_command") -> Observation:
    return Observation(
        id=f"obs_{id(node_id)}",
        investigation_id=inv_id,
        node_id=node_id,
        source_tool=tool,
        obs_type="command_result",
        payload={"exit_code": 0, "stdout": "ok", "stderr": ""},
        created_at=datetime.now(timezone.utc),
    )


def _claim(inv_id: str, claim_type: str, key: str, value) -> Claim:
    import uuid
    return Claim(
        id=f"cl_{uuid.uuid4().hex[:6]}",
        investigation_id=inv_id,
        claim_type=claim_type,
        key=key,
        value=value,
        created_at=datetime.now(timezone.utc),
    )


def _ev(claim_id: str, obs_ids: list[str], tier: str = "execution") -> Evidence:
    import uuid
    return Evidence(
        id=f"ev_{uuid.uuid4().hex[:6]}",
        claim_id=claim_id,
        observation_ids=obs_ids,
        support_type="support",
        source_tier=tier,
        created_at=datetime.now(timezone.utc),
    )


# ── Report generation ─────────────────────────────────────────────────────────

class TestReportGeneration:
    def test_report_has_header(self, tmp_path):
        inv = _inv(tmp_path)
        graph = InvestigationGraph(inv.id)
        obs = _obs(inv.id, "node_001")
        kg = KnowledgeGraph(inv.id)

        md = report_module.generate(inv, graph, [obs], kg)
        assert "# Verification Report" in md
        assert inv.id in md
        assert inv.repository_path in md

    def test_report_has_executive_summary(self, tmp_path):
        inv = _inv(tmp_path)
        graph = InvestigationGraph(inv.id)
        obs = _obs(inv.id, "node_001")
        kg = KnowledgeGraph(inv.id)

        # Insert a high-trust claim
        cl = _claim(inv.id, "RUNTIME", "language", "Python")
        ev = _ev(cl.id, [obs.id], "execution")
        kg.insert(cl, ev)

        md = report_module.generate(inv, graph, [obs], kg)
        assert "Verdict" in md
        assert "RUNTIME" in md

    def test_a_file_read_is_not_presented_as_a_finding(self, tmp_path):
        """The summary says what the run learned, not which files it opened.

        Claims are admitted in order and every read lands at the same trust, so
        the reads took all five summary slots and the report led with a list of
        paths. A reader asking what the project does was told what the Runtime
        did instead. The claim is still in the Evidence Index below — the audit
        belongs there.
        """
        inv = _inv(tmp_path)
        graph = InvestigationGraph(inv.id)
        obs = _obs(inv.id, "node_001", tool="read_file")
        kg = KnowledgeGraph(inv.id)

        read = _claim(inv.id, "FILE_READ", "server/index.js", True)
        kg.insert(read, _ev(read.id, [obs.id], "config_parse"))
        tech = _claim(inv.id, "RUNTIME", "node_version", "22")
        kg.insert(tech, _ev(tech.id, [obs.id], "execution"))

        md = report_module.generate(inv, graph, [obs], kg)
        summary = md.split("## Verdict")[1].split("---")[0]
        assert "node_version" in summary
        assert "server/index.js" not in summary
        # Still reported, in the section that indexes the evidence.
        assert "server/index.js" in md.split("## Evidence Index")[1]

    def test_a_run_that_only_read_files_does_not_claim_a_confidence_problem(self, tmp_path):
        """Reads and nothing else is not the same failure as low belief.

        One message covered both, so a run that never got past looking was
        described as one whose claims fell below the belief threshold — which
        points the reader at the wrong thing entirely.
        """
        inv = _inv(tmp_path)
        graph = InvestigationGraph(inv.id)
        obs = _obs(inv.id, "node_001", tool="read_file")
        kg = KnowledgeGraph(inv.id)

        read = _claim(inv.id, "FILE_READ", "server/index.js", True)
        kg.insert(read, _ev(read.id, [obs.id], "config_parse"))

        md = report_module.generate(inv, graph, [obs], kg)
        summary = md.split("## Verdict")[1].split("---")[0]
        assert "belief threshold" not in summary
        assert "read" in summary, summary

    def test_what_the_run_did_outranks_what_it_read(self, tmp_path):
        """A run asked to operate the app must report whether the operating worked.

        Claims are admitted in plan order — every read and every page-reach
        before the first click — so an admission-ordered summary spent all five
        slots on the manifest parses and the URL it navigated to, and the
        browser's account of pressing the sign-in button arrived after the cut.
        The reader got a report whose headline was `PACKAGE name` and which
        never mentioned that the sign-in had been attempted at all.
        """
        inv = _inv(tmp_path)
        graph = InvestigationGraph(inv.id)
        obs = _obs(inv.id, "node_001", tool="browser_click")
        kg = KnowledgeGraph(inv.id)

        # Admitted first: six read/parse claims, all above threshold, which is
        # more than the summary has room for.
        for i in range(6):
            c = _claim(inv.id, "PACKAGE", f"field_{i}", f"value_{i}")
            kg.insert(c, _ev(c.id, [obs.id], "config_parse"))
        pressed = _claim(inv.id, "INTERACTION", "effect:role=button[name=\"Sign in\"]",
                         "unchanged")
        kg.insert(pressed, _ev(pressed.id, [obs.id], "execution"))

        md = report_module.generate(inv, graph, [obs], kg)
        summary = md.split("## Verdict")[1].split("---")[0]
        assert "Sign in" in summary, summary

    def test_one_finding_is_not_reported_once_per_sighting(self, tmp_path):
        """Re-observing a claim does not make it five findings.

        Every browser action re-reports where the page is, so a five-step
        interaction files five `WEB current_url` claims at the top trust. Listed
        separately they took every summary slot between them and the summary
        became one sentence said five times. The Evidence Index keeps all five,
        which is where an audit of when the page was read belongs.
        """
        inv = _inv(tmp_path)
        graph = InvestigationGraph(inv.id)
        obs = _obs(inv.id, "node_001")
        kg = KnowledgeGraph(inv.id)

        for _ in range(5):
            c = _claim(inv.id, "WEB", "current_url", "http://localhost:5173/login")
            kg.insert(c, _ev(c.id, [obs.id], "execution"))
        other = _claim(inv.id, "INTERACTION", "interacted:role=button", True)
        kg.insert(other, _ev(other.id, [obs.id], "execution"))

        md = report_module.generate(inv, graph, [obs], kg)
        summary = md.split("## Verdict")[1].split("---")[0]
        assert summary.count("current_url") == 1, summary
        assert "interacted:role=button" in summary, summary

    def test_what_happened_outranks_that_something_happened(self, tmp_path):
        """The click's outcome must survive a run of types, not fall off the end.

        Every control touched files one `interacted:<control> = True` claim
        alongside the claims that say what the touch did. Arrival order put the
        bookkeeping first, so the two typed fields filled the summary and the
        press of the submit button — the only claim in the run that says whether
        any of it worked — was the sixth row and never printed.
        """
        inv = _inv(tmp_path)
        graph = InvestigationGraph(inv.id)
        obs = _obs(inv.id, "node_001", tool="browser_click")
        kg = KnowledgeGraph(inv.id)

        for field in ("Email", "Password"):
            touched = _claim(inv.id, "INTERACTION", f"interacted:{field}", True)
            kg.insert(touched, _ev(touched.id, [obs.id], "execution"))
            value = _claim(inv.id, "INTERACTION", f"field_value:{field}", "x")
            kg.insert(value, _ev(value.id, [obs.id], "execution"))
        submit = _claim(inv.id, "INTERACTION", "effect:submit", "unchanged")
        kg.insert(submit, _ev(submit.id, [obs.id], "execution"))

        md = report_module.generate(inv, graph, [obs], kg)
        summary = md.split("## Verdict")[1].split("---")[0]
        assert "effect:submit" in summary, summary
        # Still recorded — the Evidence Index is where every claim appears.
        assert "interacted:Email" in md.split("## Evidence Index")[1]

    def test_report_has_technologies_section(self, tmp_path):

        inv = _inv(tmp_path)
        graph = InvestigationGraph(inv.id)
        obs = _obs(inv.id, "node_001")
        kg = KnowledgeGraph(inv.id)

        cl = _claim(inv.id, "RUNTIME", "node_version", "18")
        kg.insert(cl, _ev(cl.id, [obs.id], "execution"))

        md = report_module.generate(inv, graph, [obs], kg)
        assert "Detected Technologies" in md
        assert "node_version" in md

    def test_report_has_goals_section(self, tmp_path):
        inv = _inv(tmp_path)
        graph = InvestigationGraph(inv.id)
        obs = _obs(inv.id, "node_001")
        kg = KnowledgeGraph(inv.id)
        goals = GoalEngine(inv.id)
        g = Goal(id="goal_001", name="Verify Runtime", required_claim_types=["RUNTIME"])
        goals.add(g)
        goals.mark_satisfied("goal_001")

        md = report_module.generate(inv, graph, [obs], kg, goals)
        assert "Goals Summary" in md
        assert "Verify Runtime" in md
        assert "satisfied" in md

    def test_report_claims_traceable(self, tmp_path, monkeypatch):
        """Build plan rule: every claim in report must trace to an observation."""
        monkeypatch.setenv("WIZARD_DATA_DIR", str(tmp_path))
        inv = _inv(tmp_path)
        graph = InvestigationGraph(inv.id)

        obs1 = _obs(inv.id, "node_001", "execute_command")
        obs2 = _obs(inv.id, "node_001", "read_file")
        kg = KnowledgeGraph(inv.id)

        cl1 = _claim(inv.id, "RUNTIME", "tests_passed", 42)
        ev1 = _ev(cl1.id, [obs1.id], "execution")
        kg.insert(cl1, ev1)

        cl2 = _claim(inv.id, "PACKAGE", "name", "my-app")
        ev2 = _ev(cl2.id, [obs2.id], "config_parse")
        kg.insert(cl2, ev2)

        # Claim with NO observation — should be excluded from evidence index
        cl3 = _claim(inv.id, "RUNTIME", "orphan", True)
        cl3_ev = _ev(cl3.id, ["obs_nonexistent_99"], "documentation")
        kg.insert(cl3, cl3_ev)

        md = report_module.generate(inv, graph, [obs1, obs2], kg)
        assert "Evidence Index" in md

        # obs1 and obs2 must appear as citations
        assert obs1.id in md
        assert obs2.id in md
        # orphan observation should NOT appear in evidence index rows
        assert "obs_nonexistent_99" not in md

    def test_report_contradictions_section(self, tmp_path):
        inv = _inv(tmp_path)
        graph = InvestigationGraph(inv.id)
        obs = _obs(inv.id, "node_001")
        kg = KnowledgeGraph(inv.id)

        cl1 = _claim(inv.id, "RUNTIME", "startup", True)
        cl2 = _claim(inv.id, "RUNTIME", "startup", False)
        kg.insert(cl1, _ev(cl1.id, [obs.id], "execution"))
        kg.insert(cl2, _ev(cl2.id, [obs.id + "_2"], "execution"))
        kg.add_relationship(cl1.id, cl2.id, "CONTRADICTS")

        md = report_module.generate(inv, graph, [obs], kg)
        assert "Contradictions" in md

    def test_report_unverified_areas(self, tmp_path):
        inv = _inv(tmp_path)
        graph = InvestigationGraph(inv.id)
        kg = KnowledgeGraph(inv.id)
        goals = GoalEngine(inv.id)
        goals.add(Goal(id="g1", name="Verify Security", required_claim_types=["SECURITY"]))
        # NOT satisfied

        md = report_module.generate(inv, graph, [], kg, goals)
        assert "Unverified Areas" in md
        assert "Verify Security" in md

    def test_report_written_to_disk(self, tmp_path, monkeypatch):
        """verification_report.md must be plain markdown text, not JSON."""
        monkeypatch.setenv("WIZARD_DATA_DIR", str(tmp_path))
        from wizard_kernel.storage import fs_store
        inv = _inv(tmp_path)
        graph = InvestigationGraph(inv.id)
        obs = _obs(inv.id, "node_001")
        kg = KnowledgeGraph(inv.id)

        md = report_module.generate(inv, graph, [obs], kg)
        fs_store.write_text(inv.id, "verification_report.md", md)

        report_file = tmp_path / "investigations" / inv.id / "verification_report.md"
        assert report_file.exists()
        content = report_file.read_text(encoding="utf-8")
        # Must be plain markdown, not JSON
        assert content.startswith("# Verification Report")
        assert "{" not in content[:20]  # not a JSON wrapper


# ── API endpoint ──────────────────────────────────────────────────────────────

class TestReportEndpoint:
    def test_report_endpoint_returns_markdown(self, tmp_path, monkeypatch):
        """GET /v1/investigations/{id}/report returns markdown when complete.

        Tests only the HTTP endpoint logic, not the background loop.
        We seed the manager directly to avoid race conditions with the
        daemon thread that starts when POST is called.
        """
        monkeypatch.setenv("WIZARD_DATA_DIR", str(tmp_path))

        from wizard_kernel.api import deps
        deps.get_manager.cache_clear()

        from wizard_kernel.contracts.status import LifecycleState
        from wizard_kernel.session.investigation import Investigation
        from wizard_kernel.storage import fs_store

        import uuid

        app = create_app()
        client = TestClient(app)

        # Seed a completed investigation directly — no background thread race
        manager = deps.get_manager()
        inv = Investigation(
            id=f"inv_{uuid.uuid4().hex[:12]}",
            repository_path=str(tmp_path),
            intent="verify",
            targets=["runtime"],
            options={},
            budget_total=10,
            budget_remaining=5,
        )
        inv.state = LifecycleState.completed
        manager._store[inv.id] = inv

        # Write the report file (what the loop would have written)
        fake_md = "# Verification Report\n\nAll good."
        fs_store.write_text(inv.id, "verification_report.md", fake_md)

        # GET report
        resp = client.get(f"/v1/investigations/{inv.id}/report")
        assert resp.status_code == 200
        data = resp.json()
        assert "report_markdown" in data
        assert data["report_markdown"].startswith("# Verification Report")
        assert data["investigation_id"] == inv.id
        assert "report_path" in data

    def test_report_returns_409_when_not_complete(self, tmp_path, monkeypatch):
        """Report endpoint must return 409 if investigation not yet complete."""
        monkeypatch.setenv("WIZARD_DATA_DIR", str(tmp_path))
        from wizard_kernel.api import deps
        deps.get_manager.cache_clear()

        app = create_app()
        client = TestClient(app)

        resp = client.post("/v1/investigations", json={
            "repository_path": str(tmp_path),
            "intent": "verify",
            "targets": [],
        })
        inv_id = resp.json()["investigation_id"]

        # Do NOT set state to completed — report must be 409
        resp = client.get(f"/v1/investigations/{inv_id}/report")
        assert resp.status_code == 409
