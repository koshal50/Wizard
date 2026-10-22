"""Stage 4 — Packager (architecture §9).

Assembles authoritative investigation state into agent context. One source of
truth, two outputs:

  * build_explorer_packet(...)   → the exact trust-stripped dict agents already
                                    consume. Moved byte-for-byte from the loop's
                                    original _build_explorer_context so the running
                                    engine (MockExplorer / HttpExplorer) is unchanged.
  * build_explorer_sections(...) → the same material as modular, priority-ranked
                                    ContextSections that drive KV-cache ordering,
                                    token-budget trimming, and audit — and become
                                    the LLM prompt once a real backend is wired.

The packet keeps the engine working today; the sections deliver the Context
Engine philosophy for tomorrow. "Safe from both sides."

Compression rule (architecture: "summaries destroy causal history"): the kernel
keeps full Observations forever; only this projection to the agent is summarised.
No raw payloads, trust scores, or graph internals ever enter a section — that is
kernel invariant 3, the same boundary _build_explorer_context already enforced.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from datetime import datetime, timezone
from wizard_kernel.contracts.actions import safe_parameters, failure_reason
from typing import TYPE_CHECKING

from wizard_kernel.context.sections import ContextSection
# Single source of truth for tool names (reuse, don't re-list) — invariant 5.
from wizard_kernel.world.tools import _REGISTERED_TOOLS

if TYPE_CHECKING:
    from wizard_kernel.belief.knowledge_graph import KnowledgeGraph
    from wizard_kernel.contracts.node import InvestigationNode
    from wizard_kernel.contracts.observation import Observation
    from wizard_kernel.control.goals import GoalEngine
    from wizard_kernel.reality.observations import ObservationStore
    from wizard_kernel.session.budget import BudgetManager
    from wizard_kernel.session.investigation import Investigation

# How much recent history the volatile sections surface (compressed).
_RECENT_OBS_N = 5
_RECENT_FAIL_N = 3

# Script name / command fragments that mark a long-running service rather than a
# one-shot task. Matched generically against the script NAME and its command, so
# it works for any ecosystem's conventions without naming a framework.
_LONG_RUNNING_HINTS = ("dev", "start", "serve", "server", "watch", "preview",
                       "up", "runserver", "--watch", "nodemon", "vite", "next ")
_ONE_SHOT_HINTS = ("build", "test", "lint", "typecheck", "format", "compile",
                   "migrate", "seed", "clean", "prepare", "check")
_CONTEXT_SECRET = re.compile(
    r"(?i)(\b(?:password|passwd|secret|token|api[_-]?key|authorization|cookie)\b\s*[:=]\s*)[^\s,;]+"
)


def _safe_preview(value: object, limit: int = 700) -> str:
    """Bound process output before it enters an agent request; hide common secrets."""
    text = str(value or "")
    text = re.sub(r"(?i)\bBearer\s+\S+", "Bearer [REDACTED]", text)
    text = _CONTEXT_SECRET.sub(r"\1[REDACTED]", text)
    return text[-limit:]


def _compact_outcome(obs: "Observation") -> str:
    """Keep decision-relevant results without repeating page schemas in history.

    The latest browser schema is already supplied in `resource_state.browser`.
    Serializing the complete browser result into `previous_actions` duplicated
    snapshots (up to 4 KB per action) in every subsequent Explorer request.
    """
    payload = obs.payload or {}
    result = {key: payload[key] for key in (
        "ok", "error", "detail", "error_type", "exit_code",
    ) if key in payload}
    for key in ("stdout", "stderr"):
        if payload.get(key):
            result[key + "_preview"] = _safe_preview(payload[key])
    data = payload.get("data")
    if isinstance(data, dict):
        keys = {
            "url", "title", "status", "status_code", "active", "host", "port",
            "pid", "is_running", "exit_code", "handle_id", "all_filled",
            "clicked", "effect", "selector_name", "submitted_form", "command", "cwd",
        }
        compact = {key: data[key] for key in keys if key in data}
        for key in ("command", "cwd"):
            if key in compact:
                compact[key] = _safe_preview(compact[key], 500 if key == "command" else 300)
        for key in ("stdout_so_far", "stderr_so_far", "stdout", "stderr"):
            if data.get(key):
                compact[key + "_preview"] = _safe_preview(data[key])
        fields = data.get("fields")
        if isinstance(fields, list):
            compact["fields"] = [
                {key: field.get(key) for key in ("selector", "typed", "error") if key in field}
                for field in fields[:12] if isinstance(field, dict)
            ]
        result["data"] = compact
    return json.dumps(result, default=str, ensure_ascii=False)[:1500]


def _classify_lifecycle(name: str, command: str) -> str:
    """"long_running" | "one_shot" | "unknown" for a declared command.

    A browse-the-app goal needs a long-running service; a build-verification goal
    is satisfied by a one-shot. The Runtime does not decide WHICH to run — it only
    surfaces the distinction so an agent can choose. Name wins when it is
    unambiguous (``dev`` is a server even if it shells out to a bundler); the
    command text is the tie-breaker.
    """
    text = f"{name} {command}".lower()
    long_hit = any(h in text for h in _LONG_RUNNING_HINTS)
    one_hit = any(h in text for h in _ONE_SHOT_HINTS)
    if long_hit and not one_hit:
        return "long_running"
    if one_hit and not long_hit:
        return "one_shot"
    # A name like "start" (long) that runs "build && node" — prefer the name.
    if any(h in name.lower() for h in _LONG_RUNNING_HINTS):
        return "long_running"
    if any(h in name.lower() for h in _ONE_SHOT_HINTS):
        return "one_shot"
    return "unknown"


def _discover_runnable_commands(repo_path: str) -> list[dict]:
    """Commands the repository itself declares, with an inferred lifecycle.

    Reads only what the repo states — currently package.json ``scripts`` at the
    root and one level of workspace-ish subdirectories — so nothing here is
    specific to any one project. Returns [] on any read/parse problem rather than
    raising: missing or malformed manifests are normal and must not break context
    assembly. Capped so a repo with dozens of scripts cannot bloat the packet.
    """
    out: list[dict] = []
    if not repo_path:
        return out
    try:
        root = Path(repo_path)
    except (TypeError, ValueError):
        return out
    candidates = [root / "package.json"]
    try:
        for child in sorted(root.iterdir()):
            if child.is_dir() and (child / "package.json").is_file():
                candidates.append(child / "package.json")
    except OSError:
        pass
    for pkg in candidates[:6]:
        try:
            data = json.loads(pkg.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            continue
        scripts = data.get("scripts") if isinstance(data, dict) else None
        if not isinstance(scripts, dict):
            continue
        where = "." if pkg.parent == root else pkg.parent.name
        for name, command in list(scripts.items())[:20]:
            out.append({
                "command": f"npm run {name}",
                "definition": str(command)[:400],
                "cwd": where,
                "lifecycle": _classify_lifecycle(str(name), str(command)),
            })
        if len(out) >= 24:
            break
    return out[:24]

# Claims at or above this belief score read as "verified"; below, "assumptions".
# Matches KnowledgeGraph.summary()'s own high-trust threshold — one source.
_VERIFIED_THRESHOLD = 0.6


def _compact(value):
    if isinstance(value, str):
        return value[:3000]
    if isinstance(value, dict):
        return {key: _compact(item) for key, item in list(value.items())[:20]
                if key.lower() not in {'password', 'token', 'secret', 'authorization'}}
    if isinstance(value, list):
        return [_compact(item) for item in value[:12]]
    return value


def _result_record(obs):
    payload = obs.payload or {}
    action = payload.get('action') or {}
    return {'observation_id': obs.id, 'node_id': obs.node_id, 'goal_id': obs.goal_id,
            'required_check': bool(payload.get('required_check')), 'evidence_categories': obs.evidence_categories,
            'tool': payload.get('tool') if obs.obs_type == 'agent_failure' else obs.source_tool,
            'params': safe_parameters(payload.get('parameters') or action.get('params') or payload.get('meta') or {}),
            'status': payload.get('status') or ('EXECUTED' if obs.success else 'FAILED'),
            'result': _compact(payload.get('data') or {k: payload[k] for k in ('stdout', 'stderr', 'exit_code') if k in payload}) if obs.success else None,
            'reason': None if obs.success else _compact(failure_reason(payload)),
            'failure_output': None if obs.success else _compact({k: payload[k] for k in ('stdout', 'stderr') if k in payload}),
            'exit_code': payload.get('exit_code', (payload.get('data') or {}).get('exit_code')),
            'provider_status': payload.get('status_code'),
            'returned_node_id': payload.get('returned_node_id'),
            'valid_node_ids': payload.get('valid_node_ids'),
            'retryable': obs.success and obs.source_tool in {'read_process', 'check_port', 'browser_snapshot', 'browser_extract'},
            'prohibited_from_repeating': not obs.success,
            'required_next_behavior': payload.get('required_next_behavior') or (None if obs.success else 'choose a materially different action or return incomplete')}


def _plan_view(inv_id, node):
    from wizard_kernel.control.investigation_graph import get_graph
    graph = get_graph(inv_id)
    nodes = graph.all_nodes() if graph else [node]
    settled = {n.id for n in nodes if n.state in {'complete', 'failed'}}
    current = graph.get(node.id) if graph else node
    return {'current_node': current.model_dump() if current else None,
            'runnable_next_nodes': [{'id': n.id, 'action': n.action}
                                    for n in nodes if n.state == 'waiting'
                                    and set(n.depends_on).issubset(settled)],
            'failed_nodes': [{'id': n.id, 'state': n.state}
                             for n in nodes if n.state == 'failed'],
            'completed_nodes': [{'id': n.id, 'state': n.state, 'executed_action': n.executed_action}
                                for n in nodes if n.state == 'complete'][-8:],
            'pending_nodes': [{'id': n.id, 'action': n.action} for n in nodes if n.state == 'waiting'][:8]}


def _process_records(observations):
    latest = {}
    for obs in observations:
        payload, data = obs.payload, obs.payload.get('data') or {}
        if obs.source_tool == 'kill_process' and obs.success:
            latest.pop(data.get('killed'), None)
        if obs.source_tool not in {'start_process', 'read_process'} or not data.get('handle_id'):
            continue
        stdout = _compact(data.get('stdout_so_far') or payload.get('stdout') or '')
        stderr = _compact(data.get('stderr_so_far') or payload.get('stderr') or '')
        latest[data['handle_id']] = {**_compact(data), 'tool': obs.source_tool,
            'observation_id': obs.id, 'inspected': obs.source_tool == 'read_process',
            'running': data.get('is_running'), 'stdout': stdout, 'stderr': stderr,
            'output_available': bool(stdout or stderr)}
    return list(latest.values())[-8:]


class Packager:
    """Builds agent context packets and sections from the loop's own handles.

    Stateless: every method reads the handles passed in and returns a fresh
    projection. It never stores or mutates investigation state.
    """

    # ── Explorer: the exact contract agents consume (invariant 3) ───────────────

    def build_explorer_packet(
        self,
        inv: "Investigation",
        node: "InvestigationNode",
        goals: "GoalEngine",
        kg: "KnowledgeGraph",
        budget: "BudgetManager",
        obs_store: "ObservationStore | None" = None,
    ) -> dict:
        """The trust-stripped context dict handed to the Explorer Agent.

        Kept byte-for-byte compatible with the original loop._build_explorer_context
        so MockExplorer / HttpExplorer behaviour does not change. Agents never
        receive trust scores, raw KG relationships, or observation internals.
        """
        observations = obs_store.all() if obs_store else []
        active_goals = []
        for goal in goals.open_goals():
            evidence = goals.evidence_status(goal.id, observations)
            active_goals.append({
                "id": goal.id,
                "name": goal.name,
                "state": goal.state,
                "required_evidence": evidence["required"],
                "completed_evidence": evidence["completed"],
                "missing_evidence": evidence["missing"],
            })
        process_observations = [
            o for o in observations if o.source_tool in {"start_process", "read_process", "kill_process", "list_processes"}
        ]
        port_observations = [
            o for o in observations
            if o.source_tool == "check_port" and (o.payload or {}).get("data", {}).get("active")
        ]
        browser_page = None
        for observation in reversed(observations):
            payload = observation.payload or {}
            if not observation.source_tool.startswith("browser_") or not payload.get("ok"):
                continue
            data = payload.get("data") or {}
            # Interactions that navigate to a new page include its freshly
            # captured snapshot. Prefer that over the older pre-click snapshot.
            page = data.get("page_observation") or data
            if isinstance(page, dict) and (page.get("snapshot") or page.get("controls")):
                browser_page = page
                break
        resource_state = {
            "process": [
                {
                    "tool": o.source_tool,
                    "handle_id": ((o.payload or {}).get("meta") or {}).get("handle_id")
                                 or (((o.payload or {}).get("data") or {}).get("handle_id")),
                    "command": _safe_preview(
                        ((o.payload or {}).get("data") or {}).get("command"), 500),
                    "cwd": _safe_preview(
                        ((o.payload or {}).get("data") or {}).get("cwd"), 300),
                    "running": (o.payload or {}).get("is_running")
                               if "is_running" in (o.payload or {})
                               else (((o.payload or {}).get("data") or {}).get("is_running")),
                    "exit_code": (((o.payload or {}).get("data") or {}).get("exit_code")),
                    "output_available": bool((o.payload or {}).get("stdout") or
                                              (o.payload or {}).get("stderr") or
                                              ((o.payload or {}).get("data") or {}).get("stdout_so_far") or
                                              ((o.payload or {}).get("data") or {}).get("stderr_so_far")),
                    "output_preview": _safe_preview(
                        ((o.payload or {}).get("data") or {}).get("stdout_so_far")
                        or ((o.payload or {}).get("data") or {}).get("stderr_so_far")
                        or (o.payload or {}).get("stdout") or (o.payload or {}).get("stderr")
                    ) if ((o.payload or {}).get("data") or {}).get("stdout_so_far")
                    or ((o.payload or {}).get("data") or {}).get("stderr_so_far")
                    or (o.payload or {}).get("stdout") or (o.payload or {}).get("stderr") else "",
                }
                for o in process_observations[-2:]
            ],
            "readiness": "reachable_endpoint_observed" if port_observations else "not_established",
            "reachable_endpoints": [
                {"host": (o.payload.get("data") or {}).get("host"),
                 "port": (o.payload.get("data") or {}).get("port")}
                for o in port_observations[-4:]
            ],
            "browser": ({
                key: (
                    value[:6000] if key == "snapshot" and isinstance(value, str)
                    else [{k: v for k, v in control.items() if k != "value"}
                          for control in value[:40] if isinstance(control, dict)]
                    if key == "controls" and isinstance(value, list)
                    else value
                )
                for key, value in browser_page.items()
                if key in {"url", "title", "snapshot", "controls", "node_count", "status"}
            } if browser_page else {"state": "no browser page schema observed"}),
            # What the repository itself says it can run. Discovered, never
            # guessed: the Explorer picked `npm run build` for a browse-the-app
            # goal because it could not see that `dev`/`start` existed — the
            # manifest exposed that package.json was present but not its scripts.
            # Each entry carries an inferred lifecycle ("long_running" vs
            # "one_shot") so an agent can prefer a server for a browser goal
            # without any framework assumption baked into the Runtime.
            "runnable_commands": _discover_runnable_commands(
                getattr(inv, "repository_path", None)),
        }
        return {
            "investigation_id": inv.id,
            "intent": inv.intent,
            'question': getattr(inv, 'question', ''),
            'deadline_at': inv.deadline_at.isoformat(),
            'investigation': {'id': inv.id, 'intent': inv.intent, 'question': getattr(inv, 'question', ''),
                              'phase': inv.state.value, 'deadline_at': inv.deadline_at.isoformat(),
                              'remaining_seconds': max(0, int((inv.deadline_at - datetime.now(timezone.utc)).total_seconds()))},
            'plan': _plan_view(inv.id, node),
            'node_selection': {'valid_node_ids': [node.id],
                               'ownership': 'Runtime reserved this node; Explorer chooses only its action'},
            'successful_results': [_result_record(o) for o in observations if o.success][-8:],
            'recent_failures': [_result_record(o) for o in observations if not o.success][-8:],
            'http': {'allowed_domains': inv.options.get('allowed_domains', []),
                     'runtime_authorized_readiness_target': (node.action.get('params') or {}).get('url') if node.action.get('readiness_check') else None,
                     'responses': [_result_record(o) for o in observations if o.source_tool == 'http_request'][-3:]},
            "targets": inv.targets,
            "browser_enabled": bool(inv.options.get("browser_enabled")),
            "current_node": {
                "id": node.id,
                "type": node.type,
                "action": node.action,
                "goal_id": node.goal_id,
            },
            "active_goals": active_goals,
            "resource_state": resource_state,
            "available_tools": sorted(
                tool for tool in _REGISTERED_TOOLS
                if inv.intent != 'explain' or tool in {'read_file', 'list_tree', 'search_files', 'path_exists'}
                if not node.action.get('runtime_required') or tool == node.action.get('tool')
                if (inv.options.get("browser_enabled") or not tool.startswith("browser_"))
                and (tool != "http_request" or inv.options.get("allowed_domains") or node.action.get('readiness_check'))
            ),
            "kg_summary": kg.summary(),
            "remaining_budget": budget.remaining,
            "previous_actions": [
                {
                    "node_id": obs.node_id,
                    "tool": ((obs.payload or {}).get("tool")
                             if getattr(obs, "obs_type", "") == "agent_failure" else obs.source_tool),
                    "parameters": (
                        (obs.payload or {}).get("parameters")
                        if getattr(obs, "obs_type", "") == "agent_failure"
                        else {
                            **((obs.payload or {}).get("meta") or {}),
                            **({key: ((obs.payload or {}).get("data") or {}).get(key)
                                for key in ("command", "cwd")
                                if ((obs.payload or {}).get("data") or {}).get(key) is not None}
                               if obs.source_tool == "start_process" else {}),
                        }
                    ) or {},
                    "outcome": _compact_outcome(obs),
                    "succeeded": (obs.payload or {}).get("ok"),
                }
                for obs in observations[-_RECENT_OBS_N:] if obs.success
                if ((obs.payload or {}).get("tool")
                    if getattr(obs, "obs_type", "") == "agent_failure" else obs.source_tool) in _REGISTERED_TOOLS
            ],
        }


    # ── Explorer: the modular section view (KV cache / budget / audit) ──────────

    def build_explorer_sections(
        self,
        inv: "Investigation",
        node: "InvestigationNode",
        goals: "GoalEngine",
        kg: "KnowledgeGraph",
        budget: "BudgetManager",
        obs_store: "ObservationStore | None" = None,
    ) -> list[ContextSection]:
        """Project the same state into priority-ranked ContextSections.

        IDs / priorities / scopes follow the built-in section table (architecture
        §9). Content is drawn only from existing handles and is compressed +
        trust-stripped, so nothing here widens what an agent can see beyond the
        packet above. `obs_store` is the one new handle the Packager needs (the
        volatile observation/failure sections); it is read-only.
        """
        summary = kg.summary()
        observations = obs_store.all() if obs_store else []
        return [
            ContextSection(
                id="system_instructions", priority=100, scope="all_agents",
                content=self._system_instructions(inv, node),
            ),
            ContextSection(
                id="available_tools", priority=90, scope="explorer_only",
                content=self._available_tools(),
            ),
            ContextSection(
                id="repository_summary", priority=80, scope="all_agents",
                content=self._repository_summary(summary),
            ),
            ContextSection(
                id="verified_claims", priority=75, scope="explorer_only",
                content=self._verified_claims(summary),
            ),
            ContextSection(
                id="unverified_assumptions", priority=70, scope="explorer_only",
                content=self._unverified_assumptions(kg),
            ),
            ContextSection(
                id="recent_observations", priority=60, scope="explorer_only",
                content=self._recent_observations(observations),
            ),
            ContextSection(
                id="recent_failures", priority=50, scope="explorer_only",
                content=self._recent_failures(observations),
            ),
            ContextSection(
                id="budget_status", priority=40, scope="explorer_only",
                content=f"BUDGET: {budget.remaining} remaining",
            ),
        ]

    # ── Section renderers ───────────────────────────────────────────────────────
    # The engine node has no free-text description/hypothesis like the doc's
    # example; we map those to the concrete fields that DO exist (intent, node
    # type, planned action).

    @staticmethod
    def _system_instructions(inv: "Investigation", node: "InvestigationNode") -> str:
        return (
            "INVESTIGATION CONTEXT\n"
            "=====================\n"
            f"INTENT: {inv.intent}\n"
            f"TARGETS: {', '.join(inv.targets) if inv.targets else '(none)'}\n"
            f"NODE: {node.id} ({node.type})\n"
            f"ACTION: {node.action}\n\n"
            "INSTRUCTION: Return a single ToolRequest with tool, parameters, and reason."
        )

    @staticmethod
    def _available_tools() -> str:
        return "AVAILABLE TOOLS\n---------------\n" + "\n".join(sorted(_REGISTERED_TOOLS))

    @staticmethod
    def _repository_summary(summary: dict) -> str:
        high_trust = summary.get("high_trust_claims", [])
        lines = [f"{c['type']}:{c['key']} = {c['value']}" for c in high_trust]
        body = "\n".join(lines) if lines else "(no high-trust claims yet)"
        return (
            "REPOSITORY OVERVIEW\n-------------------\n"
            f"Claims known: {summary.get('claims_count', 0)}\n"
            f"{body}"
        )

    @staticmethod
    def _verified_claims(summary: dict) -> str:
        # Trust bucket comes through as the VERIFIED label; the raw score stays
        # kernel-side (invariant 3).
        high_trust = summary.get("high_trust_claims", [])
        body = "\n".join(
            f"VERIFIED: {c['type']}:{c['key']} = {c['value']}" for c in high_trust
        )
        return "VERIFIED KNOWLEDGE\n------------------\n" + (body or "(none yet)")

    @staticmethod
    def _unverified_assumptions(kg: "KnowledgeGraph") -> str:
        lines = [
            f"? {c.claim_type}:{c.key} = {c.value}"
            for c in kg.all_claims()
            if kg.trust_of(c.id) < _VERIFIED_THRESHOLD
        ]
        return "UNVERIFIED ASSUMPTIONS\n----------------------\n" + ("\n".join(lines) or "(none)")

    @classmethod
    def _recent_observations(cls, observations: list["Observation"]) -> str:
        lines = [cls._summarize_obs(o) for o in observations[-_RECENT_OBS_N:]]
        return "RECENT OBSERVATIONS\n-------------------\n" + ("\n".join(lines) or "(none)")

    @classmethod
    def _recent_failures(cls, observations: list["Observation"]) -> str:
        fails = [o for o in observations if (o.payload or {}).get("ok") is False]
        lines = [f"FAILED: {o.source_tool} → {cls._failure_reason(o)}" for o in fails[-_RECENT_FAIL_N:]]
        return "RECENT FAILURES\n---------------\n" + ("\n".join(lines) or "(none)")

    @staticmethod
    def _summarize_obs(obs: "Observation") -> str:
        payload = obs.payload or {}
        extra = f" exit={payload['exit_code']}" if "exit_code" in payload else ""
        return f"{obs.obs_type} via {obs.source_tool}: ok={payload.get('ok')}{extra}"

    @staticmethod
    def _failure_reason(obs: "Observation") -> str:
        payload = obs.payload or {}
        if payload.get("error"):
            return str(payload["error"])
        if payload.get("exit_code") is not None:
            return f"exit {payload['exit_code']}"
        return "unknown"
