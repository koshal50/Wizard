"""Small, durable, secret-aware trace of one investigation's data flow.

This is intentionally a boundary trace, not a prompt logger. It records the
shape and outcome of decisions so a failed run can be reconstructed without
copying prompts, credentials, form values, or full tool output.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from wizard_kernel.storage import fs_store

_SECRET_KEY = re.compile(r"password|secret|token|authorization|cookie|api.?key|credential", re.I)
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(\b(?:password|passwd|secret|token|api[_-]?key|authorization|cookie)\b\s*[:=]\s*)[^\s,;]+"
)
_LABELED_SECRET = re.compile(
    r"(?i)((?:password|passwd|passcode|secret|token|api[_-]?key|authorization|cookie)[A-Za-z0-9_ -]{0,40}[\"']?\s*[:=]\s*)[^\s,;\"'}]+"
)
_BEARER = re.compile(r"(?i)\bBearer\s+[^\s,;]+")
_QUOTED_SECRET = re.compile(r'''(?i)((?:password|passwd|passcode|secret|token|api[_-]?key|authorization|cookie)[^:\n]{0,40}[:=]\s*)(["'])(.*?)\2''')
_EMAIL = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_ANSI = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
_MAX_TEXT = 600


def fingerprint(value: Any) -> str:
    raw = json.dumps(_safe(value), sort_keys=True, default=str, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:16]


def _safe_url(value: str) -> str:
    try:
        parts = urlsplit(value)
        if not parts.scheme or not parts.netloc:
            return value
        host = parts.hostname or ""
        if parts.port:
            host += f":{parts.port}"
        query = "[REDACTED]" if parts.query else ""
        return urlunsplit((parts.scheme, host, parts.path, query, ""))
    except (ValueError, TypeError):
        return "[REDACTED URL]"


def safe_text(value: Any, *, key: str = "", limit: int = _MAX_TEXT) -> str:
    text = str(value)
    if _SECRET_KEY.search(key):
        return "[REDACTED]"
    text = _ANSI.sub("", text)
    text = _BEARER.sub("Bearer [REDACTED]", text)
    text = _QUOTED_SECRET.sub(r"\1\2[REDACTED]\2", text)
    text = _SECRET_ASSIGNMENT.sub(r"\1[REDACTED]", text)
    text = _LABELED_SECRET.sub(r"\1[REDACTED]", text)
    text = _EMAIL.sub("[EMAIL]", text)
    text = re.sub(r"(?i)(https?://)[^/@\s]+:[^/@\s]+@", r"\1[REDACTED]@", text)
    text = re.sub(r"(?i)(https?://[^\s?#]+)\?[^\s#]+", r"\1?[REDACTED]", text)
    if len(text) > limit:
        text = text[:limit] + "…"
    return text


def _safe(value: Any, key: str = "") -> Any:
    if _SECRET_KEY.search(key) or key.lower() in {"value", "values", "typed_text", "form_data"}:
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): _safe(v, str(k)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(v, key) for v in value[:40]]
    if isinstance(value, str):
        if value.startswith(("http://", "https://")):
            return _safe_url(value)
        if key.lower() in {"url", "target_url", "endpoint"}:
            return _safe_url(value)
        return safe_text(value, key=key)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return safe_text(value, key=key)


def safe_parameters(parameters: Any) -> dict:
    """Keep useful action structure; never record entered values."""
    if not isinstance(parameters, dict):
        return {"shape": type(parameters).__name__}
    result = {}
    for key, value in parameters.items():
        name = str(key)
        if _SECRET_KEY.search(name) or name.lower() in {"value", "values", "text", "typed_text", "form_data"}:
            result[name] = "[REDACTED]"
        elif name.lower() == "fields" and isinstance(value, list):
            result[name] = [
                {k: ("[REDACTED]" if _SECRET_KEY.search(str(k)) or str(k).lower() in {"value", "text"}
                     else safe_text(v, key=str(k)) if isinstance(v, str) else type(v).__name__)
                 for k, v in field.items()}
                if isinstance(field, dict) else type(field).__name__
                for field in value[:20]
            ]
        elif isinstance(value, str):
            result[name] = _safe_url(value) if name.lower() in {"url", "endpoint"} else safe_text(value, key=name)
        elif isinstance(value, dict):
            result[name] = safe_parameters(value)
        elif isinstance(value, list):
            result[name] = [_safe(item, name) for item in value[:20]]
        else:
            result[name] = value
    return result


def node_summary(node: Any) -> dict:
    action = getattr(node, "action", None) or {}
    params = action.get("params") or {}
    safe_action = {"tool": action.get("tool"), "params": safe_parameters(params)}
    return {
        "id": getattr(node, "id", None),
        "type": getattr(node, "type", None),
        "goal_id": getattr(node, "goal_id", None),
        "depends_on": list(getattr(node, "depends_on", []) or []),
        "planned_tool": action.get("tool"),
        "planned_parameter_names": sorted(map(str, params.keys())) if isinstance(params, dict) else [],
        "action_fingerprint": fingerprint(safe_action),
        "planned_parameters": safe_parameters(params),
    }


def context_summary(context: dict, observations: list[Any] | None = None) -> dict:
    goals = context.get("active_goals") or []
    current = context.get("current_node") or {}
    resources = context.get("resource_state") or {}
    previous = context.get("previous_actions") or []
    observation_list = observations or []
    pages = []
    browser = resources.get("browser") or {}
    if isinstance(browser, dict):
        pages.append({
            "state": browser.get("state"),
            "url": _safe_url(str(browser["url"])) if browser.get("url") else None,
            "title": safe_text(browser.get("title", "")),
            "snapshot_chars": len(str(browser.get("snapshot", ""))),
            "controls": [
                {"role": c.get("role"), "name": safe_text(c.get("name", ""))}
                for c in (browser.get("controls") or [])[:30] if isinstance(c, dict)
            ],
        })
    summary = {
        "keys": sorted(map(str, context.keys())),
        "context_chars": len(json.dumps(context, default=str, ensure_ascii=False)),
        "intent": safe_text(context.get("intent", "")),
        "question": safe_text(context.get("question", ""), key="question"),
        "targets": [_safe_url(str(t)) if str(t).startswith(("http://", "https://")) else safe_text(t)
                    for t in (context.get("targets") or [])[:20]],
        "node": {"id": current.get("id"), "type": current.get("type"),
                 "goal_id": current.get("goal_id"),
                 "planned_tool": (current.get("action") or {}).get("tool")},
        "goals": [{"id": g.get("id"), "name": safe_text(g.get("name", "")),
                   "required": g.get("required_evidence", []),
                   "completed": g.get("completed_evidence", []),
                   "missing": g.get("missing_evidence", [])}
                  for g in goals[:30] if isinstance(g, dict)],
        "available_tools": context.get("available_tools", []),
        "process_state": [{k: p.get(k) for k in ("tool", "handle_id", "running", "output_available")}
                          for p in (resources.get("process") or [])[-4:] if isinstance(p, dict)],
        "reachable_endpoints": resources.get("reachable_endpoints", [])[-8:],
        "browser": pages,
        "previous_actions": [{"node_id": a.get("node_id"), "tool": a.get("tool"),
                              "succeeded": a.get("succeeded"),
                              "observation_ids": [o.id for o in observation_list
                                                  if o.node_id == a.get("node_id")
                                                  and o.source_tool == a.get("tool")],
                              "outcome_chars": len(str(a.get("outcome", ""))),
                              "result": _previous_outcome(a.get("outcome", ""))}
                             for a in previous[-8:] if isinstance(a, dict)],
    }
    summary["context_sha256_16"] = fingerprint(summary)
    return summary


def _previous_outcome(raw: Any) -> dict:
    try:
        result = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):
        return {"summary": safe_text(raw)} if raw else {}
    if not isinstance(result, dict):
        return {"shape": type(result).__name__}
    data = result.get("data") or {}
    summary = {k: _safe(result.get(k), k) for k in ("ok", "error", "detail", "error_type", "exit_code")
               if k in result}
    if isinstance(data, dict):
        summary["data"] = {k: (_safe_url(str(v)) if k in {"url", "endpoint"} and v else _safe(v, k))
                            for k, v in data.items()
                            if k in {"url", "title", "status", "active", "host", "port", "pid",
                                     "is_running", "exit_code", "handle_id", "all_filled", "clicked", "effect"}}
        if data.get("stderr_so_far") or data.get("stdout_so_far"):
            summary["process_output"] = safe_text(
                data.get("stderr_so_far") or data.get("stdout_so_far"))[:300]
        if data.get("snapshot"):
            summary["snapshot_chars"] = len(str(data["snapshot"]))
        fields = data.get("fields")
        if fields:
            summary["fields"] = [{"selector": safe_text(f.get("selector", "")),
                                   "typed": f.get("typed"), "error": safe_text(f.get("error") or "")}
                                  for f in fields[:20] if isinstance(f, dict)]
    return summary


def planner_context_summary(context: dict) -> dict:
    page_controls = context.get("page_controls") or []
    return {
        "keys": sorted(map(str, context.keys())),
        "chars": len(json.dumps(context, default=str, ensure_ascii=False)),
        "sha256_16": fingerprint(context),
        "reason": safe_text(context.get("reason", "")),
        "intent": safe_text(context.get("intent", "")),
        "question": safe_text(context.get("question", ""), key="question"),
        "targets": context.get("targets", []),
        "goal_technology": safe_text(context.get("goal_technology", "")),
        "missing_requirements": [{k: safe_text(v, key=k) if isinstance(v, str) else v
                                   for k, v in item.items()
                                   if k in {"goal_id", "goal_name", "claim_type", "description"}}
                                  for item in (context.get("missing_requirements") or [])[:40]
                                  if isinstance(item, dict)],
        "file_observation_ids": context.get("file_observation_ids", {}),
        "parsed_observation_ids": context.get("parsed_observation_ids", {}),
        "queued_read_paths": context.get("queued_read_paths", []),
        "visited_urls": context.get("visited_urls", []),
        "page_url": context.get("page_url"),
        "page_fingerprint": context.get("page_fingerprint"),
        "page_controls": [{"role": c.get("role"), "name": safe_text(c.get("name", "")),
                           "input_type": c.get("input_type"),
                           "value_present": bool(c.get("value")),
                           "disabled": c.get("disabled")}
                          for c in page_controls[:30] if isinstance(c, dict)],
        "browser_enabled": context.get("browser_enabled"),
        "budget_remaining": context.get("budget_remaining"),
    }


def observation_summary(obs: Any) -> dict:
    payload = getattr(obs, "payload", {}) or {}
    data = payload.get("data") or {}
    summary: dict[str, Any] = {
        "observation_id": getattr(obs, "id", None),
        "node_id": getattr(obs, "node_id", None),
        "goal_id": getattr(obs, "goal_id", None),
        "tool_request_id": getattr(obs, "tool_request_id", None),
        "execution_id": getattr(obs, "execution_id", None),
        "tool": getattr(obs, "source_tool", None),
        "observation_type": getattr(obs, "obs_type", None),
        "evidence_categories": getattr(obs, "evidence_categories", []),
        "success": getattr(obs, "success", False),
        "payload_keys": sorted(payload.keys()),
        "error": safe_text(payload.get("error") or payload.get("detail") or ""),
    }
    if isinstance(data, dict):
        summary["result"] = {
            k: _safe_url(str(v)) if k in {"url", "endpoint"} and v else safe_text(v, key=k)
            for k, v in data.items() if k in {"url", "title", "status", "active", "host", "port", "pid", "is_running", "exit_code", "handle_id", "all_filled", "clicked", "effect"}
        }
        for out_key in ("stdout_so_far", "stderr_so_far", "stdout", "stderr"):
            if data.get(out_key):
                output = safe_text(data[out_key], key=out_key)
                summary[f"{out_key}_preview"] = output[:300]
                summary[f"{out_key}_chars"] = len(str(data[out_key]))
        if data.get("snapshot"):
            summary["page_snapshot_chars"] = len(str(data["snapshot"]))
        controls = data.get("controls") or (data.get("page_observation") or {}).get("controls") or []
        if controls:
            summary["controls"] = [{"role": c.get("role"), "name": safe_text(c.get("name", "")),
                                    "input_type": c.get("input_type"), "disabled": c.get("disabled")}
                                   for c in controls[:30] if isinstance(c, dict)]
        fields = data.get("fields")
        if fields:
            summary["fields"] = [{"selector": safe_text(f.get("selector", "")),
                                   "typed": f.get("typed"), "error": safe_text(f.get("error") or "")}
                                  for f in fields[:20] if isinstance(f, dict)]
    return summary


def record(inv_id: str, stage: str, **details: Any) -> None:
    """Append one bounded JSONL stage record; tracing never breaks an investigation."""
    try:
        row = {"at": datetime.now(timezone.utc).isoformat(), "stage": stage,
               "investigation_id": inv_id, **_safe(details)}
        path = fs_store.ensure(inv_id) / "flow_trace.jsonl"
        with path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    except Exception:  # noqa: BLE001 - observability must not alter Runtime behavior
        return


def goal_states(goal_engine: Any, observations: list[Any]) -> list[dict]:
    """Include the concrete observation IDs behind each completed category."""
    from wizard_kernel.control.goals import evidence_satisfies_requirement

    result = []
    for goal in goal_engine.all():
        status = goal_engine.evidence_status(goal.id, observations)
        sources = {}
        for category in status["completed"]:
            sources[category] = [
                {"observation_id": obs.id, "node_id": obs.node_id,
                 "tool": obs.source_tool, "success": obs.success}
                for obs in observations
                if obs.goal_id == goal.id and evidence_satisfies_requirement(obs, category)
            ]
        result.append({
            "id": goal.id,
            "name": safe_text(goal.name),
            "state": goal.state,
            "required_claim_types": list(goal.required_claim_types),
            "required": status["required"],
            "completed": status["completed"],
            "missing": status["missing"],
            "evidence_sources": sources,
        })
    return result


def plan_summary(plan: Any) -> dict:
    return {
        "technologies": [{
            "name": safe_text(t.name),
            "goals": [{"name": safe_text(g.name),
                       "required_claim_types": list(g.required_claim_types),
                       "required_evidence": list(g.required_evidence)}
                      for g in t.initial_goals],
        } for t in plan.technologies],
        "seed_nodes": [node_summary(n) for n in plan.seed_nodes],
    }
