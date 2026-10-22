"""Read-only runbook projection of recorded checks and executions."""
from __future__ import annotations

import html
from wizard_kernel.control import flow_trace


def project(inv, state):
    checks = []
    required = set(state.get("required_check_ids", [c["id"] for c in state.get("checks", [])]))
    for check in state.get("checks", []):
        result = state.get("results", {}).get(check["id"], {})
        proofs = []
        for assertion in result.get("assertions", []):
            if assertion.get("actual") is None:
                continue
            actual = str(assertion.get("actual", ""))
            expected = str(assertion.get("assertion", {}).get("expected", ""))
            offset = actual.find(expected) if expected and assertion.get("verdict") == "passed" else -1
            start = max(0, offset - 40)
            proofs.append({"observed": flow_trace.safe_text(actual[start:start + max(180, len(expected) + 40)]),
                           "observation_id": assertion.get("observation_id"), "verdict": assertion.get("verdict")})
        checks.append({"id": check["id"], "description": flow_trace.safe_text(check["description"]),
                       "purpose": "goal" if check["id"] in required else "recovery_helper",
                       "status": {"passed": "VERIFIED", "failed": "FAILED"}.get(result.get("status"), "UNVERIFIED"),
                       "requirements": flow_trace.safe_parameters({"assertions": check.get("assertions", [])})["assertions"], "evidence": proofs,
                       "missing_evidence": [{"reason": flow_trace.safe_text(str(a.get("reason") or "Predicate not satisfied")),
                                             "superseded_by": a.get("superseded_by")}
                                            for a in result.get("assertions", []) if a.get("verdict") != "passed"],
                       "blocker": flow_trace.safe_text(str(result.get("reason") or ""))})
    steps = [{key: execution.get(key) for key in ("id", "check_id", "tool", "parameters", "state", "success", "observation_id")}
             for execution in state.get("executions", [])]
    return {"schema_version": 1, "investigation_id": inv.id, "state": inv.state.value,
            "request": flow_trace.safe_text(inv.question or " ".join([inv.intent, *inv.targets]), limit=8000),
            "checks": checks, "artifacts": state.get("artifacts", []),
            "recovery": state.get("recovery_round"), "required_check_ids": state.get("required_check_ids", [c["id"] for c in checks]),
            "steps": [{**step, "parameters": flow_trace.safe_parameters(step["parameters"] or {})} for step in steps], "cleanup": flow_trace.safe_text(str(state.get("cleanup", "Pending"))),
            "stop_reason": flow_trace.safe_text(str(state.get("stop_reason") or "")),
            "model_calls": state.get("model_calls", 0), "provider_requests": state.get("provider_requests", 0)}


def markdown(data):
    def text(value):
        return str(value).replace("\n", " ").replace("`", "'")
    checks = data["checks"]
    goals = [c for c in checks if c.get("purpose", "goal") == "goal"]
    lines = ["# Wizard project runbook", "", text(data["request"]), "",
             f"Investigation: `{data['investigation_id']}`", f"State: {data['state']}", "",
             "## Verification summary", "",
             f"{sum(c['status'] == 'VERIFIED' for c in goals)} verified / {sum(c['status'] == 'FAILED' for c in goals)} failed / {sum(c['status'] == 'UNVERIFIED' for c in goals)} unverified", ""]
    for check in checks:
        lines += ["### " + ("Recovery helper: " if check.get("purpose") == "recovery_helper" else "") + text(check["description"]), "", "**" + check["status"] + "**", ""]
        for requirement in check["requirements"]:
            lines += ["- Required: " + text(requirement.get("source", "")) + " / " + text(requirement.get("field", "")) + " " + text(requirement.get("operator", "")) + " " + text(requirement.get("expected", ""))]
        for proof in check["evidence"]:
            lines += ["- Observed: " + text(proof["observed"]), "  Evidence: `" + text(proof["observation_id"] or "not recorded") + "`"]
        if check["blocker"]:
            lines += ["- Missing / blocker: " + text(check["blocker"])]
        for missing in check.get("missing_evidence", []):
            lines += ["- Missing evidence: " + text(missing["reason"])]
        if not check["evidence"]:
            lines += ["- No compatible execution evidence recorded."]
        lines += [""]
    lines += ["## How this project was run", "", "Recorded commands below are execution history. Cleanup may have stopped the services; they are not a claim of current availability.", ""]
    commands = [s for s in data["steps"] if s["tool"] in {"start_process", "execute_command"}]
    for step in commands:
        params = step["parameters"] or {}
        lines += ["### " + text(step["tool"]), "", "- Working directory: `" + text(params.get("cwd", "repository root")) + "`",
                  "- Result: " + ("executed successfully" if step["success"] else "failed" if step["success"] is False else "not observed"),
                  "", "```text", text(params.get("command", "Command not recorded")), "```", ""]
    if not commands:
        lines += ["No startup command was executed. Startup has not been verified.", ""]
    lines += ["## Recorded workflow", "", "Read these steps to reproduce the investigation. A rerun must create a fresh investigation; browser element references and sessions must not be replayed.", ""]
    for index, step in enumerate(data["steps"], 1):
        status = "success" if step["success"] else "failed" if step["success"] is False else step["state"]
        lines += [f"{index}. `{text(step['tool'])}` - {text(status)}; evidence `{text(step['observation_id'] or 'not recorded')}`"]
    lines += ["", "## Execution map", "", "Each recorded action connects its check to an observation; this is an execution map, not an inferred application architecture.", "", "```text"]
    for step in data["steps"]:
        lines.append(text(step["check_id"]) + " -> " + text(step["tool"]) + " -> " + text(step["observation_id"] or "not observed"))
    lines += ["```"]
    architecture = data.get("application_map")
    if architecture:
        lines += ["", "## Application map", "", "Source-supported relationships are inferred, not proof of runtime connectivity.", ""]
        labels = {node["id"]: node["label"] for node in architecture.get("nodes", [])}
        for node in architecture.get("nodes", []):
            lines += ["- " + text(node["label"]) + ": `" + text(node.get("path") or "") + "`"]
        for edge in architecture.get("relationships", []):
            lines += ["- " + text(labels.get(edge["source"], edge["source"])) + " -> " + text(labels.get(edge["target"], edge["target"])) + " (" + text(edge.get("classification", "inferred")) + ")"]
        if not architecture.get("relationships"):
            lines += ["No component connections were established by this investigation."]
    lines += ["", "## Run details", "", f"Decision requests: {data['model_calls']}", f"Provider HTTP attempts: {data['provider_requests']}",
              "Cleanup: " + text(data["cleanup"]), "", "Local process execution is not container isolation."]
    if data["stop_reason"]:
        lines += ["", "Stopped: " + text(data["stop_reason"])]
    if data.get("recovery"):
        lines += ["", "## Recovery work", "", text(data["recovery"]["reason"]),
                  "Original verification requirements were retained. Helper results are diagnostic prerequisites, not substitute goal proofs."]
    if data.get("artifacts"):
        lines += ["", "## Captured screenshots", "", "Captured artifacts are supporting records, not automatic visual verification."]
        for artifact in data["artifacts"]:
            lines += ["- " + text(artifact["path"]) + " — observation `" + text(artifact["observation_id"]) + "`"]
    return "\n".join(lines) + "\n"


def architecture_svg(graph):
    """Render the existing evidence-backed graph locally; no inferred new edges."""
    esc = lambda value: html.escape(str(value), quote=True)
    nodes = graph.get("nodes", [])[:60]
    positions = {node["id"]: ((i % 3) * 310 + 10, (i // 3) * 110 + 15) for i, node in enumerate(nodes)}
    height = max(100, ((len(nodes) + 2) // 3) * 110)
    parts = [f'<svg role="img" aria-label="Source-supported application map" viewBox="0 0 940 {height}" xmlns="http://www.w3.org/2000/svg">']
    for edge in graph.get("relationships", []):
        if edge["source"] in positions and edge["target"] in positions:
            x1, y1 = positions[edge["source"]]
            x2, y2 = positions[edge["target"]]
            parts.append(f'<path d="M{x1 + 140} {y1 + 60} L{x2 + 140} {y2}" stroke="#9475c5" stroke-dasharray="5 4" fill="none"><title>{esc(edge.get("description", "Source-supported connection"))}</title></path>')
    for node in nodes:
        x, y = positions[node["id"]]
        parts += [f'<rect x="{x}" y="{y}" width="280" height="60" rx="8" fill="#f0ecff"><title>{esc(node.get("description", ""))}</title></rect>',
                  f'<text x="{x + 10}" y="{y + 25}" font-size="14">{esc(node["label"][:35])}</text>',
                  f'<text x="{x + 10}" y="{y + 45}" font-size="11">{esc(str(node.get("path") or "")[:42])}</text>']
    parts.append('</svg>')
    return ''.join(parts)


def html_report(data):
    """Self-contained offline report. All observed text is escaped, never executable."""
    esc = lambda value: html.escape(str(value), quote=True)
    cards = []
    for check in data["checks"]:
        proofs = "".join("<li>" + esc(p["observed"]) + "<br><code>" + esc(p["observation_id"] or "not recorded") + "</code></li>" for p in check["evidence"])
        cards.append('<article><h3>' + ('Recovery helper: ' if check.get('purpose') == 'recovery_helper' else '') + esc(check["description"]) + '</h3><strong>' + esc(check["status"]) + '</strong><ul>' + proofs + '</ul><p>' + esc(check["blocker"]) + '</p></article>')
    commands = []
    for step in data["steps"]:
        if step["tool"] in {"start_process", "execute_command"}:
            params = step["parameters"] or {}
            commands.append('<article><h3>' + esc(step["tool"]) + '</h3><p>Working directory: <code>' + esc(params.get("cwd", "repository root")) + '</code></p><pre>' + esc(params.get("command", "not recorded")) + '</pre><p>Execution: ' + esc("successful" if step["success"] else "failed" if step["success"] is False else "not observed") + '</p></article>')
    # Vertical SVG remains readable offline and can be enlarged without a diagram service.
    height = max(70, len(data["steps"]) * 88)
    svg = [f'<svg role="img" aria-label="Recorded execution map" viewBox="0 0 920 {height}" xmlns="http://www.w3.org/2000/svg">']
    for i, step in enumerate(data["steps"]):
        y = i * 88 + 10
        labels = [step["check_id"] or "discovery", step["tool"], step["observation_id"] or "not observed"]
        for j, label in enumerate(labels):
            x = j * 310
            svg += [f'<rect x="{x}" y="{y}" width="285" height="55" rx="8" fill="#f0ecff"/>',
                    f'<text x="{x + 12}" y="{y + 32}" font-size="13">{esc(label)}</text>']
            if j < 2:
                svg.append(f'<path d="M{x + 285} {y + 28}h25l-7 -5m7 5l-7 5" stroke="#555" fill="none"/>')
    svg.append('</svg>')
    timeline = "".join('<li><code>' + esc(s["tool"]) + '</code> - ' + esc("success" if s["success"] else "failed" if s["success"] is False else s["state"]) + ' - evidence <code>' + esc(s["observation_id"] or "not recorded") + '</code></li>' for s in data["steps"])
    captures = ''.join('<figure><img loading="lazy" style="max-width:100%" src="artifacts/' + esc(data["investigation_id"]) + '/' + esc(a["path"]) + '" alt="Captured browser state"><figcaption>Observation <code>' + esc(a["observation_id"]) + '</code></figcaption></figure>' for a in data.get("artifacts", []))
    architecture = data.get("application_map") or {}
    components = architecture.get("nodes", [])
    source_map = ''
    if components:
        labels = {n["id"]: n["label"] for n in components}
        source_map = '<h2>Application map</h2><p>Observed repository components. Source-supported connections are inferred, not proof of a runtime connection.</p><ul>'
        source_map += ''.join('<li>' + esc(n["label"]) + ' <code>' + esc(n.get("path") or "") + '</code></li>' for n in components) + '</ul>'
        source_map += '<div class="map">' + architecture_svg(architecture) + '</div>'
        source_map += '<ul>' + ''.join('<li>' + esc(labels.get(e["source"], e["source"])) + ' &rarr; ' + esc(labels.get(e["target"], e["target"])) + ' (' + esc(e.get("classification", "inferred")) + ')</li>' for e in architecture.get("relationships", [])) + '</ul>'
        if not architecture.get("relationships"):
            source_map += '<p>No component connections were established.</p>'
    return ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Wizard project runbook</title>'
            '<style>body{max-width:1100px;margin:2rem auto;padding:1rem;font:16px/1.6 system-ui;color:#222;background:#faf9fd}nav{display:flex;gap:1rem;flex-wrap:wrap}article{background:white;border:1px solid #ddd;border-radius:10px;padding:1rem;margin:1rem 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f0ecff;padding:1rem}code{overflow-wrap:anywhere}svg{width:100%;min-width:700px}.map{overflow:auto}a{color:#6141af}</style>'
            '<h1>Wizard project runbook</h1><p>' + esc(data["request"]) + '</p><p>State: <strong>' + esc(data["state"]) + '</strong> | Investigation: <code>' + esc(data["investigation_id"]) + '</code></p>'
            '<nav><a href="#results">Results</a><a href="#start">How to run</a><a href="#map">Execution map</a><a href="#steps">Recorded workflow</a></nav>'
            '<h2 id="results">Verification results</h2>' + ''.join(cards) + '<h2 id="start">How this project was run</h2><p>Recorded history, not a promise that services are still running. Review working directories and redacted values before reproducing.</p>' + (''.join(commands) or '<p>No startup command was executed.</p>') +
            '<h2 id="map">Execution map</h2><p>Actual recorded check-to-tool-to-observation links. This does not infer unobserved application connections.</p><div class="map">' + ''.join(svg) + '</div>' +
            source_map + '<h2 id="steps">Recorded workflow</h2><ol>' + timeline + '</ol>' + captures + '<h2>Cleanup and blockers</h2><p>' + esc(data["cleanup"]) + '</p><p>' + esc(data["stop_reason"]) + '</p><p>Local process execution is not container isolation. Rerunning uses a fresh investigation and fresh browser state.</p></html>')


def persist(inv, state):
    from wizard_kernel.storage import fs_store
    data = project(inv, state)
    if getattr(inv, "repository_path", None) and data["state"] in {"completed", "incomplete", "failed", "cancelled"}:
        try:
            from wizard_kernel.session.architecture import export_architecture
            data["application_map"] = export_architecture(inv)
        except (ImportError, OSError, ValueError, KeyError, TypeError):
            data["application_map_unavailable"] = True
    fs_store.write(inv.id, "runbook.json", data)
    fs_store.write_text(inv.id, "runbook.html", html_report(data))
    return data
