"""Contract schema tests — all Pydantic models serialize correctly."""
from datetime import datetime, timezone
import pytest
from wizard_kernel.contracts.request import InvestigationRequest, InvestigationOptions
from wizard_kernel.contracts.observation import Observation
from wizard_kernel.contracts.claim import Claim
from wizard_kernel.contracts.evidence import Evidence
from wizard_kernel.contracts.node import (
    InvestigationNode, Hypothesis, HypothesisKind, ClaimTemplate,
)
from wizard_kernel.contracts.manifest import RepositoryManifest
from wizard_kernel.contracts.plan import TechnologyPlan, TechnologyEntry


def test_request_defaults():
    req = InvestigationRequest(
        repository_path="/tmp/repo", intent="verify", targets=["runtime"]
    )
    assert req.contracts_version == "1.0"
    assert req.options.budget == 40
    assert req.options.sandbox_mode == "local_dev"
    assert req.options.planner_url is None


def test_request_roundtrip():
    req = InvestigationRequest(
        repository_path="C:/repos/proj", intent="investigate", targets=["architecture"]
    )
    data = req.model_dump()
    req2 = InvestigationRequest.model_validate(data)
    assert req2.repository_path == req.repository_path


def test_node_defaults():
    node = InvestigationNode(
        id="n_001", type="execute",
        action={"tool": "execute_command", "params": {"command": "npm install"}},
        hypothesis=Hypothesis(
            kind=HypothesisKind.exit_code_in, success_values=[0], failure_values=[1]
        ),
        on_success=ClaimTemplate(claim_type="DEPS", key="installable", value=True),
    )
    assert node.state == "waiting"
    assert node.depends_on == []
    assert node.claim_ids == []


def test_node_roundtrip():
    node = InvestigationNode(
        id="n_002", type="read",
        action={"tool": "read_file", "params": {"path": "package.json"}},
        hypothesis=Hypothesis(kind=HypothesisKind.always_success),
    )
    data = node.model_dump()
    node2 = InvestigationNode.model_validate(data)
    assert node2.id == node.id
    assert node2.hypothesis.kind == HypothesisKind.always_success


def test_manifest_schema():
    m = RepositoryManifest(
        investigation_id="inv_001", root_path="/tmp",
        total_files=10, total_dirs=3,
        key_files=["package.json"], extensions={"js": 5, "json": 2},
        directory_tree=["src/", "src/index.js"], size_bytes_approx=4096,
    )
    assert m.total_files == 10
    assert "package.json" in m.key_files


def test_claim_schema():
    c = Claim(
        id="cl_001", investigation_id="inv_001",
        claim_type="RUNTIME", key="language", value="Node.js",
        created_at=datetime.now(timezone.utc),
    )
    assert c.claim_type == "RUNTIME"


def test_evidence_schema():
    e = Evidence(
        id="ev_001", claim_id="cl_001", observation_ids=["obs_001"],
        support_type="support", source_tier="execution",
        created_at=datetime.now(timezone.utc),
    )
    assert e.source_tier == "execution"


from wizard_kernel.contracts.plan import TechnologyPlan, TechnologyEntry, GoalDefinition


def test_technology_plan_schema():
    plan = TechnologyPlan(technologies=[
        TechnologyEntry(
            name="Node.js", confidence="high",
            signals=["package.json"],
            initial_goals=[GoalDefinition(name="Verify Runtime", required_claim_types=["RUNTIME"])],
        )
    ])
    assert plan.technologies[0].name == "Node.js"
    assert plan.seed_nodes == []
