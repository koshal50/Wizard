"""Render saved investigations without executing actions or changing their state.

Usage: python regenerate.py DATA_ROOT ARCHITECTURE_ID API_ID INCOMPLETE_RUNTIME_ID
Requires the Runtime src directory on PYTHONPATH. Originals are never overwritten.
"""

import json
import os
import sys
from pathlib import Path

from wizard_kernel.belief.knowledge_graph import KnowledgeGraph, Relationship
from wizard_kernel.contracts.claim import Claim
from wizard_kernel.contracts.evidence import Evidence
from wizard_kernel.contracts.node import InvestigationNode
from wizard_kernel.contracts.observation import Observation
from wizard_kernel.control.goals import GoalEngine
from wizard_kernel.control.investigation_graph import InvestigationGraph
from wizard_kernel.control.report import generate
from wizard_kernel.session.manager import _from_dict


def render_saved(root, investigation_id):
    directory = root / "investigations" / investigation_id
    inv = _from_dict(json.loads((directory / "meta.json").read_text(encoding="utf-8")))
    observations = [
        Observation.model_validate(json.loads(p.read_text(encoding="utf-8")))
        for p in sorted((directory / "observations").glob("*.json"))
    ]
    graph = InvestigationGraph(inv.id)
    for node in json.loads((directory / "investigation_graph.json").read_text(encoding="utf-8")):
        graph.add(InvestigationNode.model_validate(node))
    data = json.loads((directory / "knowledge_graph.json").read_text(encoding="utf-8"))
    kg = KnowledgeGraph(inv.id)
    # Restore persisted scores exactly; inserting evidence would recompute them.
    kg._claims = {c["id"]: Claim.model_validate(c) for c in data["claims"]}
    kg._evidence = {
        cid: [Evidence.model_validate(e) for e in rows] for cid, rows in data["evidence"].items()
    }
    kg._trust = data["trust"]
    kg._rels = [
        Relationship(from_id=r["from"], to_id=r["to"], rel_type=r["type"], id=r["id"])
        for r in data.get("relationships", [])
    ]
    goals = GoalEngine(inv.id)
    goals.restore()
    return generate(inv, graph, observations, kg, goals)


if __name__ == "__main__":
    root = Path(sys.argv[1]).resolve()
    os.environ["WIZARD_DATA_DIR"] = str(root)
    for name, investigation_id in zip(
        ("architecture", "api", "incomplete-runtime"), sys.argv[2:], strict=True
    ):
        destination = Path(__file__).parent / f"{name}.md"
        destination.write_text(render_saved(root, investigation_id), encoding="utf-8")
        print(destination.name)
