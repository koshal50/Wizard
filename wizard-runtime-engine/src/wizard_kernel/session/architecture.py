"""Export existing investigation evidence; never inspect the repository again."""
import json
import re
from pathlib import Path

from backend.architecture import ArchitectureGraph, Located

from wizard_kernel.control.flow_trace import safe_text
from wizard_kernel.storage import fs_store


def action_label(kind, label):
    """Express the supported relation kind as an action, never invent behavior."""
    label = str(label or kind)
    if re.match(r"(?i)^(imports?|requests?|sends?|loads?|reads?|writes?|stores?|queries|calls?|uses?|registers?|starts?|builds?|configures?|authenticates?|provides?|refreshes?|validates?|creates?|connects?)\b", label):
        return label
    verb = {"http": "requests", "http-request": "requests", "query": "queries", "calls": "calls",
            "imports": "imports", "stores": "stores", "build": "builds"}.get(str(kind).casefold())
    if not verb:
        return label
    if verb == "requests":
        label = re.sub(r"(?i)\s+HTTP$", " API", label)
    if verb == "queries":
        label = re.sub(r"(?i)\s+(?:queries|query)$", "", label)
    return verb + " " + label


def export_architecture(inv):
    state = fs_store.read(inv.id, "verification.json") or {}
    observations = []
    for file in sorted((fs_store.inv_dir(inv.id) / "observations").glob("*.json")):
        obs = json.loads(file.read_text(encoding="utf-8"))
        if obs.get("success") and obs.get("source_tool") == "read_file":
            observations.append(obs)

    def relative(value):
        value = str(value).replace("\\", "/")
        root = str(inv.repository_path).replace("\\", "/").rstrip("/")
        if value.casefold().startswith(root.casefold() + "/"):
            value = value[len(root) + 1:]
        value = value.rstrip("/")
        Located(path=value)  # Reject traversal or paths outside this repository.
        return value

    def text(value):
        value = str(value).replace(str(inv.repository_path), "[repository]").replace(
            str(inv.repository_path).replace("\\", "/"), "[repository]")
        value = re.sub(r"(?i)([a-z][a-z0-9+.-]*://)[^/@\s]+:[^/@\s]+@", r"\1[REDACTED]@", value)
        return safe_text(value, limit=2000)

    evidence, by_obs = [], {}
    predicates = {}
    for result in state.get("results", {}).values():
        for checked in result.get("assertions", []):
            assertion = checked.get("assertion", {})
            if (checked.get("verdict") == "passed" and assertion.get("field") == "content"
                    and assertion.get("operator") == "contains"):
                predicates.setdefault(checked.get("observation_id"), []).append(assertion.get("expected", ""))
    for obs in observations:
        data = obs.get("payload", {}).get("data") or {}
        try:
            path = relative(data.get("path", ""))
        except ValueError:
            continue
        # No source code, command output, environment, or raw observations leave the machine.
        row = {"id": obs["id"], "description": "Repository file read during the local investigation.",
               "classification": "observed", "path": path}
        content = str(data.get("content", ""))
        verified = [str(p) for p in predicates.get(obs["id"], []) if p and len(str(p)) <= 160 and str(p) in content]
        if verified:
            description = "; ".join(dict.fromkeys(verified[:4]))
            safe_description = text(description)
            row["description"] = ("Verified file content: " + safe_description if safe_description == description
                                  else "Content predicate verified; sensitive values omitted.")
            offset = content.index(verified[0])
            row["line_start"] = content[:offset].count("\n") + int(data.get("start_line") or 1)
            row["line_end"] = row["line_start"] + verified[0].count("\n")
        evidence.append(row)
        by_obs[obs["id"]] = row
    diagram = state.get("architecture_diagram") or {}
    nodes, edges = [], []
    for c in diagram.get("components", []):
        refs = list(dict.fromkeys(i for i in c["observation_ids"] if i in by_obs))
        try:
            path = relative(c["path"])
        except ValueError:
            continue
        if not refs or not any(by_obs[i]["path"] == path or by_obs[i]["path"].startswith(path + "/") for i in refs):
            continue
        nodes.append({"id": c["id"], "label": text(c["label"]), "type": text(c["type"]), "path": path,
                      "description": text(c["description"]), "evidence_ids": refs})
    ids = {n["id"] for n in nodes}
    for c in diagram.get("connections", []):
        refs = list(dict.fromkeys(i for i in c["observation_ids"] if i in by_obs))
        if c["source"] in ids and c["target"] in ids and refs:
            edges.append({"id": c["id"], "source": c["source"], "target": c["target"], "type": text(c["type"]),
                          "description": text(c["description"]), "label": text(action_label(c["type"], c.get("label")))[:120], "evidence_ids": refs, "classification": "inferred"})
    # Older investigations have no semantic synthesis. Show only measured files;
    # never manufacture service dependencies from the investigation execution DAG.
    if not nodes:
        paths = {}
        for e in evidence:
            paths.setdefault(e["path"], []).append(e["id"])
        nodes = [{"id": f"file_{i}", "label": Path(p).name, "type": "file", "path": p,
                  "description": "Observed repository file.", "evidence_ids": refs}
                 for i, (p, refs) in enumerate(paths.items())]
    groups, limitations = [], []
    if "architecture_coverage" in state:
        from wizard_kernel.control.architecture_coverage import enrich_graph
        manifest = fs_store.read(inv.id, "manifest.json") or {}
        nodes, edges, groups, limitations = enrich_graph(nodes, edges, evidence, observations,
            state["architecture_coverage"], manifest.get("directory_tree", []))
    coverage = None
    if "architecture_coverage" in state:
        from wizard_kernel.control.architecture_hierarchy import abstract_graph, measured_coverage
        paths = manifest.get("directory_tree", [])
        if diagram.get("subsystems"):
            nodes, edges, coverage, warnings = abstract_graph(nodes, edges, evidence, diagram, observations, paths, text)
            groups = []
            limitations.extend(warnings)
        else:
            coverage = measured_coverage(paths, observations, evidence)
            limitations.append("This result has no semantic subsystem synthesis; legacy boundaries are presentation groups only.")
    used = {i for row in nodes + edges + groups for i in row["evidence_ids"]}
    evidence = list({e["id"]: e for e in evidence if e["id"] in used}.values())
    return ArchitectureGraph.model_validate({
        "title": "Architecture: " + Path(inv.repository_path).name,
        "repository_name": Path(inv.repository_path).name,
        "status": "completed" if inv.state == "completed" else "incomplete",
        "nodes": nodes, "relationships": edges, "evidence": evidence,
        "groups": groups, "limitations": limitations, "coverage": coverage,
    }).model_dump()
