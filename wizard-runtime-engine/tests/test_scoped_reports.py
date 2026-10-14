"""Template layout, command scope and read-only evidence projection."""

import ast
from datetime import UTC, datetime
from pathlib import Path

import pytest

from wizard_kernel.belief.knowledge_graph import KnowledgeGraph
from wizard_kernel.contracts.claim import Claim
from wizard_kernel.contracts.evidence import Evidence
from wizard_kernel.contracts.observation import Observation
from wizard_kernel.contracts.status import LifecycleState
from wizard_kernel.control.goals import Goal, GoalEngine
from wizard_kernel.control.investigation_graph import InvestigationGraph
from wizard_kernel.control.report import generate
from wizard_kernel.control.report_scope import COMMAND_TARGETS, TARGET_SECTIONS, report_contract
from wizard_kernel.control.scoped_report import ReportContext, validated_model_findings
from wizard_kernel.session.investigation import Investigation


def fixture(tmp_path, command="investigate", target="architecture"):
    inv = Investigation(
        id="inv_scoped_fixture",
        repository_path=str(tmp_path),
        intent=command,
        targets=[target] if target else [],
        options={},
        state=LifecycleState.incomplete,
    )

    def obs(name, path, content):
        return Observation(
            id=f"obs_{name}",
            investigation_id=inv.id,
            node_id=name,
            source_tool="read_file",
            obs_type="file_content",
            success=True,
            evidence_categories=["repository_read"],
            created_at=datetime.now(UTC),
            payload={"ok": True, "data": {"path": path, "content": content}},
        )

    observations = [
        obs(
            "server",
            "service/server.js",
            "const api = require('./api');\nconst web = require('express');\napp.listen(config.port);",
        ),
        obs(
            "api",
            "service/api.js",
            "const router = express.Router();\nrouter.get('/items/:id', requireAuth, (req, res) => {\nconst {name} = req.body;\nres.status(200).json({id:req.params.id});\n});\n",
        ),
        obs(
            "manifest",
            "package.json",
            '{"engines":{"node":">=18"},"dependencies":{"express":"^4","unrelated-library":"^1"},"scripts":{"start":"node service/server.js","build":"vite build"}}',
        ),
    ]
    goals = GoalEngine(inv.id)
    goals.add(
        Goal(
            "goal_fixture",
            "Inspect " + (target or "existing state"),
            ["FILE_READ"],
            required_evidence=["repository_read"],
        )
    )
    kg = KnowledgeGraph(inv.id)
    claim = Claim(
        id="cl_framework",
        investigation_id=inv.id,
        claim_type="FRAMEWORK",
        key="framework",
        value="Express",
        created_at=datetime.now(UTC),
    )
    kg.insert(
        claim,
        Evidence(
            id="ev_framework",
            claim_id=claim.id,
            observation_ids=["obs_manifest"],
            source_tier="config_parse",
            support_type="support",
            created_at=datetime.now(UTC),
        ),
    )
    return inv, InvestigationGraph(inv.id), observations, kg, goals


def test_mapping_matches_authoritative_cli():
    path = Path(__file__).resolve().parents[2] / "wizard/cli/parser/command_parser.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    assignment = next(
        n
        for n in tree.body
        if isinstance(n, ast.AnnAssign) and getattr(n.target, "id", "") == "COMMAND_TARGETS"
    )
    assert {k: list(v) for k, v in COMMAND_TARGETS.items()} == ast.literal_eval(assignment.value)
    assert set(TARGET_SECTIONS) == set().union(*map(set, COMMAND_TARGETS.values()))


@pytest.mark.parametrize(
    "command,target",
    [(c, t) for c, targets in COMMAND_TARGETS.items() for t in targets] + [("report", None)],
)
def test_every_command_target_uses_template_and_own_sections(tmp_path, command, target):
    inv, graph, obs, kg, goals = fixture(tmp_path, command, target)
    markdown = generate(inv, graph, obs, kg, goals)
    common = [
        "Executive Summary",
        "Investigation Overview",
        "Goal Verification",
        "Findings",
        "Evidence and Provenance",
        "Contradictions and Uncertainty",
        "Runtime Activity",
        "Limitations and Next Steps",
        "Investigation Graph",
    ]
    for heading in common:
        assert f"## {heading}" in markdown
    if target:
        for heading in TARGET_SECTIONS[target]:
            assert f"### {heading}" in markdown
    assert "{{" not in markdown and "{=html}" not in markdown
    assert markdown.count("<details>") == markdown.count("</details>")
    assert "**Status:** `INCOMPLETE`" in markdown
    assert report_contract(inv)["command"] == command
    for line in markdown.splitlines():
        if line.startswith("| "):
            assert line.endswith(" |")


def test_architecture_is_focused_and_does_not_dump_dependencies(tmp_path):
    inv, graph, obs, kg, goals = fixture(tmp_path)
    body = generate(inv, graph, obs, kg, goals).split("## Goal Verification")[0]
    assert "Major components and responsibilities" in body
    assert "Observed source import" in body and "./api" in body
    assert "unrelated-library" not in body
    assert "Runtime verification levels" not in body and "Routes and handlers" not in body
    assert "Declared build commands" not in body


def test_api_routes_have_sources_but_no_invented_execution(tmp_path):
    inv, graph, obs, kg, goals = fixture(tmp_path, target="api")
    body = generate(inv, graph, obs, kg, goals).split("## Goal Verification")[0]
    assert "GET" in body and "/items/:id" in body and "service/api.js:" in body
    assert "requireAuth" in body and "obs_api" in body
    assert "Source-discovered; not verified" in body and "Schema not established" not in body
    assert "Application stack" not in body and "Runtime verification levels" not in body


def test_client_get_and_commented_routes_are_not_server_routes(tmp_path):
    inv, graph, obs, kg, goals = fixture(tmp_path, target="api")
    original = obs[1]
    obs[1] = original.model_copy(
        update={
            "payload": {
                "ok": True,
                "data": {
                    "path": "api.js",
                    "content": "axios.get('/client-request');\n// app.get('/comment');\napp.get('/actual', handler);",
                },
            }
        }
    )
    body = generate(inv, graph, obs, kg, goals).split("## Goal Verification")[0]
    assert "/actual" in body and "/client-request" not in body and "/comment" not in body


def test_route_contracts_do_not_leak_between_handlers(tmp_path):
    from wizard_kernel.control.scoped_report import routes

    inv, graph, obs, kg, goals = fixture(tmp_path, target="api")
    obs[1] = obs[1].model_copy(
        update={
            "payload": {
                "ok": True,
                "data": {
                    "path": "api.js",
                    "content": "app.get('/literal', (req, res) => { res.status(201).json({ok:true}); });\n"
                    "app.get('/reference', namedHandler);\nfunction unrelated(req,res) { res.status(500).json(req.body.secret); }",
                },
            }
        }
    )
    found = routes(ReportContext.extract(inv, graph, obs, kg, goals))
    assert "201" in found[0]["block"] and "500" not in found[0]["block"]
    assert "secret" not in found[1]["block"] and "500" not in found[1]["block"]


def test_verification_failure_and_foreign_evidence_are_not_promoted(tmp_path):
    inv, graph, obs, kg, goals = fixture(tmp_path, "verify", "runtime")
    failed = Observation(
        id="obs_timeout",
        investigation_id=inv.id,
        node_id="check",
        source_tool="execute_command",
        obs_type="command_result",
        created_at=datetime.now(UTC),
        payload={"ok": False, "error": "timeout after 30s", "exit_code": -1},
        success=False,
    )
    foreign = obs[0].model_copy(update={"id": "obs_foreign", "investigation_id": "inv_other"})
    before = (inv.state, goals.all()[0].state, kg.trust_of("cl_framework"))
    markdown = generate(inv, graph, [*obs, failed, foreign], kg, goals)
    assert "**Status:** `INCOMPLETE`" in markdown
    assert "timeout after 30s" in markdown and "obs_foreign" not in markdown
    assert before == (inv.state, goals.all()[0].state, kg.trust_of("cl_framework"))
    assert "### Declared dependencies" not in markdown


def test_contradictions_and_real_trust_are_retained(tmp_path):
    inv, graph, obs, kg, goals = fixture(tmp_path)
    second = Claim(
        id="cl_conflict",
        investigation_id=inv.id,
        claim_type="FRAMEWORK",
        key="framework",
        value="Other",
        created_at=datetime.now(UTC),
    )
    kg.insert(
        second,
        Evidence(
            id="ev_conflict",
            claim_id=second.id,
            observation_ids=["obs_manifest"],
            source_tier="config_parse",
            support_type="contradict",
            created_at=datetime.now(UTC),
        ),
    )
    kg.add_relationship("cl_framework", "cl_conflict", "CONTRADICTS")
    markdown = generate(inv, graph, obs, kg, goals)
    assert "Unresolved" in markdown and "cl_conflict" in markdown and "ev_conflict" in markdown
    assert str(kg.trust_of("cl_framework")) in markdown and "config_parse" in markdown


def test_model_scope_citations_and_status_are_validated(tmp_path):
    inv, graph, obs, kg, goals = fixture(tmp_path)
    ctx = ReportContext.extract(inv, graph, obs, kg, goals)
    assert validated_model_findings(
        ctx,
        "# Verification Findings\n\nThe entry source initializes the application (`obs_server`).",
    )
    for invalid in [
        "# Verification Findings\n\nUncited assertion.",
        "# Verification Findings\n\nEvidence obs_foreign proves it.",
        "# Deployment execution\n\nDeployment works obs_server.",
        "# Verification Findings\n\nAll goals verified obs_server.",
        "# Verification Findings\n\n`invented.js` was inspected obs_server.",
    ]:
        assert not validated_model_findings(ctx, invalid)


def test_empty_report_and_explain_remain_read_only(tmp_path, monkeypatch):
    for command in ("report", "explain"):
        inv, graph, _, _, _ = fixture(
            tmp_path, command, "architecture" if command == "explain" else None
        )
        markdown = generate(inv, graph, [])
        assert "**Status:** `INCOMPLETE`" in markdown
        assert "Not established from the collected evidence." in markdown
        assert inv.nodes_completed == 0 and inv.model_calls == 0
