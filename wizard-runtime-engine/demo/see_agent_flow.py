"""see_agent_flow.py — a real, LLM-free, end-to-end run of the Wizard Runtime Kernel.

Run it with ``python serve_live.py``. That prints a link; open the link and watch.

WHAT THIS IS
------------
Nothing here reimplements the kernel. Every plan, agent response, request body and
status comparison is built out of ``wizard_kernel``'s own types, and every list this
module reports on is read off the kernel's own declarations rather than restated.
The kernel is driven through its public HTTP API and through the three agent seams
it already defines:

    planner_url          -> ports.planner.HttpPlanner   -> /plan/initial|next|interpret
    agent_explorer_url   -> ports.agents.HttpExplorer   -> /agent/explorer
    agent_verifier_url   -> ports.agents.HttpVerifier   -> /agent/verifier

Those three services are implemented below as **deterministic rule engines**. There
is no LLM, no sampling, no model call anywhere. Every decision is a pure function of
the context the kernel handed over, and each is written to an append-only trace
(``/flow/trace``) with the rules that produced it — so the dashboard's left pane
shows real reasoning, not narration invented afterwards.

WHAT IT USES FROM ``wizard_kernel``
----------------------------------
contracts  InvestigationNode, Hypothesis, HypothesisKind, ClaimTemplate,
           TechnologyPlan, TechnologyEntry, GoalDefinition, ToolRequest,
           ExplorerResponse, VerifierAssessment, RepositoryManifest, Observation,
           InvestigationRequest, InvestigationOptions, LifecycleState,
           ReportResponse, ToolResult, CommandResult, BackgroundProcess, Evidence,
           and every Literal taxonomy (NodeType, NodeState, ObsType, SourceTier,
           SupportType, GoalState, MatchResult, RelType, Scope)
world      sandbox.get_sandbox + SandboxRuntime driven directly (section 0 below),
           ToolExecutor, tools._REGISTERED_TOOLS, browser.get_runtime, scanner,
           repository.validate
control    ToolRequestValidator (the Explorer self-checks with the kernel's own
           validator), hypothesis.evaluate, priority.next_ready, loop constants
belief     trust.compute / source_tier_for_tool / SOURCE_WEIGHTS / U0, extractors
context    sections.estimate_tokens, Scope
session    events constants, storage.fs_store for reading artifacts back off disk

NO FALLBACK
-----------
``loop._resolve_tool_action`` falls back to a node's own action when the Explorer
errors or is refused. That is kernel safety code (invariant 4) and stays. The
Explorer here is written so it never fires: before answering it runs its request
through ``ToolRequestValidator`` — the same class, same allowlist the kernel applies
a moment later — and records the verdict. The terminal report then FAILs the run if
any ``agent.decided`` event carries ``source == "node_plan"``. Measured, not claimed.

INVARIANTS
----------
These agents live outside the kernel and stay outside it: they never write a graph,
never touch trust, never mark a goal, never execute a tool. Observations, claims,
trust, goal state and the report come only from the kernel. Where this module calls
``trust`` or ``hypothesis``, it calls pure functions on values it already holds, to
explain a decision or cross-check the kernel's output — never to author state.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, get_args

import httpx
from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, PlainTextResponse

# ── The kernel: contracts ─────────────────────────────────────────────────────
from wizard_kernel.contracts.agent import ExplorerResponse, ToolRequest, VerifierAssessment
from wizard_kernel.contracts.evidence import Evidence, SourceTier, SupportType
from wizard_kernel.contracts.manifest import RepositoryManifest
from wizard_kernel.contracts.node import (
    ClaimTemplate, Hypothesis, HypothesisKind, InvestigationNode, NodeState, NodeType,
)
from wizard_kernel.contracts.observation import ObsType, Observation
from wizard_kernel.contracts.plan import GoalDefinition, TechnologyEntry, TechnologyPlan
from wizard_kernel.contracts.process import BackgroundProcess
from wizard_kernel.contracts.report import ReportResponse
from wizard_kernel.contracts.request import InvestigationOptions, InvestigationRequest
from wizard_kernel.contracts.status import LifecycleState
from wizard_kernel.contracts.tool import CommandResult, ToolResult

# ── The kernel: engines, world, control, storage ───────────────────────────────
from wizard_kernel.belief import extractors as kernel_extractors
from wizard_kernel.belief import trust as kernel_trust
from wizard_kernel.belief.knowledge_graph import RelType
from wizard_kernel.context.sections import Scope, estimate_tokens
from wizard_kernel.control import hypothesis as kernel_hypothesis
from wizard_kernel.control import loop as kernel_loop
from wizard_kernel.control.goals import GoalState
from wizard_kernel.control.hypothesis import MatchResult
from wizard_kernel.control.priority import next_ready
from wizard_kernel.control.tool_validator import (
    ToolRequestValidator, ValidationResult,
    _ALLOWED_TOOLS, _BROWSER_TOOLS, _EXEC_TOOLS, _PATH_TOOLS, _URL_TOOLS,
)
from wizard_kernel.session import events as kernel_events
from wizard_kernel.storage import fs_store
from wizard_kernel.world import browser as kernel_browser
from wizard_kernel.world import repository as kernel_repository
from wizard_kernel.world import scanner as kernel_scanner
from wizard_kernel.world.sandbox import SandboxRuntime, get_sandbox
from wizard_kernel.world.tools import ToolExecutor, _REGISTERED_TOOLS

HERE = Path(__file__).resolve().parent

# Every tool the kernel registers — read off the registry, never restated, so a tool
# added to the kernel shows up as an uncovered gap instead of silently vanishing.
ALL_TOOLS: tuple[str, ...] = tuple(sorted(_REGISTERED_TOOLS))

# Marker placed in InvestigationRequest.targets. `targets` is the only free-form
# channel reaching the Planner on its first call (/plan/initial fires before the POST
# response returns), so capability selection has to travel there — InvestigationOptions
# is a closed model and drops unknown keys.
TARGET_BROWSER = "@plane:browser"
TARGET_FILES = "@plane:filesystem"


# ══════════════════════════════════════════════════════════════════════════════
#  Kernel surface inventory — derived from the kernel's own declarations
# ══════════════════════════════════════════════════════════════════════════════
# The verification report measures coverage against this. Because every entry is
# read out of wizard_kernel at import time, the report cannot drift from what the
# kernel actually exposes.

def _event_constants() -> dict[str, str]:
    return {name: value for name, value in vars(kernel_events).items()
            if name[:1].isupper() and isinstance(value, str) and "." in value}


KERNEL_SURFACE: dict[str, Any] = {
    "tools": ALL_TOOLS,
    "hypothesis_kinds": tuple(k.value for k in HypothesisKind),
    "node_types": get_args(NodeType),
    "node_states": get_args(NodeState),
    "obs_types": get_args(ObsType),
    "lifecycle_states": tuple(s.value for s in LifecycleState),
    "match_results": get_args(MatchResult),
    "source_tiers": get_args(SourceTier),
    "support_types": get_args(SupportType),
    "goal_states": get_args(GoalState),
    "relationship_types": get_args(RelType),
    "context_scopes": get_args(Scope),
    "event_types": _event_constants(),
    "source_weights": dict(kernel_trust.SOURCE_WEIGHTS),
    "prior_uncertainty_u0": kernel_trust.U0,
    "validator_allowed": tuple(sorted(_ALLOWED_TOOLS)),
    "validator_browser": tuple(sorted(_BROWSER_TOOLS)),
    "validator_path": tuple(sorted(_PATH_TOOLS)),
    "validator_url": tuple(sorted(_URL_TOOLS)),
    "validator_exec": tuple(sorted(_EXEC_TOOLS)),
    "verifier_interval": kernel_loop._VERIFIER_INTERVAL,
    "tool_to_obs_type": dict(kernel_loop._TOOL_TO_OBS_TYPE),
    "extractor_obs_types": tuple(sorted(kernel_extractors._REGISTRY)),
    "sandbox_methods": tuple(m for m in dir(SandboxRuntime) if not m.startswith("_")),
    "data_root": str(fs_store.data_root()),
}


def expected_belief(tier: SourceTier, support: SupportType = "support") -> float:
    """Belief one piece of evidence at `tier` yields — computed by the kernel's own
    trust engine on a throwaway Evidence value. Pure function, writes nothing."""
    from datetime import datetime, timezone
    ev = Evidence(id="ev_probe", claim_id="claim_probe", observation_ids=["obs_probe"],
                  support_type=support, source_tier=tier,
                  created_at=datetime.now(timezone.utc))
    return round(kernel_trust.compute([ev]), 3)


# ══════════════════════════════════════════════════════════════════════════════
#  Runtime configuration (set once by serve_live before the server starts)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class FlowConfig:
    host: str = "127.0.0.1"
    port: int = 8090
    repo_path: str = str(HERE)
    think_ms: int = 240          # deliberate pacing so a human can follow the stream
    poll_timeout_s: int = 480    # hard ceiling on the whole run

    @property
    def base(self) -> str:
        return f"http://{self.host}:{self.port}"


CFG = FlowConfig()


def configure(**kwargs: Any) -> FlowConfig:
    for k, v in kwargs.items():
        if v is not None:
            setattr(CFG, k, v)
    return CFG


# ══════════════════════════════════════════════════════════════════════════════
#  Agent trace — append-only, sequence-numbered, per investigation
# ══════════════════════════════════════════════════════════════════════════════
# The kernel's EventBus is authoritative and agents may not write to it
# (invariant 3), so the agents keep their own log here. The dashboard interleaves
# both streams and labels every row with its source, so it is never ambiguous who
# said what.

@dataclass
class TraceEntry:
    seq: int
    inv_id: str
    agent: str          # planner | explorer | verifier | sandbox | flow
    kind: str
    title: str
    detail: str = ""
    rules: list[str] = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    ts: float = 0.0

    def as_dict(self) -> dict:
        return {"seq": self.seq, "inv_id": self.inv_id, "agent": self.agent,
                "kind": self.kind, "title": self.title, "detail": self.detail,
                "rules": self.rules, "meta": self.meta, "ts": self.ts}



class TraceStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: list[TraceEntry] = []
        self._seq = 0
        self.viewer_seen_at: float = 0.0

    def add(self, inv_id: str, agent: str, kind: str, title: str, detail: str = "",
            rules: list[str] | None = None, meta: dict | None = None) -> TraceEntry:
        with self._lock:
            self._seq += 1
            e = TraceEntry(seq=self._seq, inv_id=inv_id, agent=agent, kind=kind,
                           title=title, detail=detail, rules=list(rules or ()),
                           meta=dict(meta or {}), ts=time.time())
            self._entries.append(e)
            return e

    def since(self, since_seq: int, inv_id: str | None = None) -> list[TraceEntry]:
        with self._lock:
            out = [e for e in self._entries if e.seq > since_seq]
        return [e for e in out if e.inv_id == inv_id] if inv_id else out

    def all_for(self, inv_id: str) -> list[TraceEntry]:
        with self._lock:
            return [e for e in self._entries if e.inv_id == inv_id]

    def mark_viewer(self) -> None:
        self.viewer_seen_at = time.time()


TRACE = TraceStore()


def _think() -> None:
    """Deliberate pacing. Not a stand-in for computation — rule evaluation is
    instant; this exists so a person can read the stream as it happens."""
    if CFG.think_ms > 0:
        time.sleep(CFG.think_ms / 1000.0)



# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 0 — the sandbox, driven directly
# ══════════════════════════════════════════════════════════════════════════════
# The kernel builds its own sandbox per investigation, inside control.loop, and
# that is what actually executes every node below. This preflight is separate and
# additional: it drives world.sandbox.SandboxRuntime and world.tools.ToolExecutor
# by hand, in this process, so the layer is exercised and reported on directly
# rather than only inferred from the kernel's results.
#
# Every method on the SandboxRuntime protocol is called here:
#   start, exec, exec_background, read_process_output, list_processes,
#   kill_process, read_file, stop
# and ToolExecutor.execute is driven with real action dicts — the same
# {"tool", "params"} shape control.loop hands it.
#
# LocalProcessRuntime is subprocess-based and documents itself as NOT secure
# isolation, so nothing here claims otherwise. The Docker runtime is probed for
# availability and reported, never silently substituted.

SANDBOX_PROBE_COMMAND = 'python -c "print(\'sandbox-preflight-ok\')"'
SANDBOX_BG_COMMAND = (
    'python -u -c "import time'
    ";[(print('preflight tick',i,flush=True),time.sleep(0.2)) for i in range(30)]\""
)


@dataclass
class SandboxProbe:
    """What the direct sandbox drive actually observed. Reported verbatim."""
    mode: str = "local_dev"
    runtime_class: str = ""
    started: bool = False
    exec_result: CommandResult | None = None
    bg_started: BackgroundProcess | None = None
    bg_polled: BackgroundProcess | None = None
    listed: int = 0
    killed: bool = False
    bytes_read: int = 0
    tool_results: dict[str, ToolResult] = field(default_factory=dict)
    docker_available: str = ""
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "mode": self.mode, "runtime_class": self.runtime_class,
            "started": self.started, "killed": self.killed,
            "bytes_read": self.bytes_read, "processes_listed": self.listed,
            "exec_exit_code": (self.exec_result.exit_code
                               if self.exec_result is not None else None),
            "exec_stdout": (self.exec_result.stdout.strip()[:200]
                            if self.exec_result is not None else ""),
            "bg_handle_id": (self.bg_started.handle_id
                             if self.bg_started is not None else ""),
            "bg_output_bytes": (len(self.bg_polled.stdout_so_far)
                                if self.bg_polled is not None else 0),
            "tools_driven": sorted(self.tool_results),
            "tools_ok": {k: v.ok for k, v in sorted(self.tool_results.items())},
            "docker_available": self.docker_available,
            "errors": self.errors,
        }



SANDBOX = SandboxProbe()


def _probe_docker() -> str:
    """Is the Docker runtime usable here? Reported, never silently substituted."""
    from wizard_kernel.world.sandbox.docker import _DEFAULT_IMAGE
    import subprocess
    try:
        r = subprocess.run(["docker", "version", "--format", "{{.Server.Version}}"],
                           capture_output=True, text=True, timeout=8)
        if r.returncode == 0 and r.stdout.strip():
            return f"docker server {r.stdout.strip()} (image {_DEFAULT_IMAGE})"
        return f"docker CLI present but no server ({(r.stderr or '').strip()[:60]})"
    except FileNotFoundError:
        return "docker CLI not installed — DockerSandboxRuntime unavailable here"
    except Exception as exc:  # noqa: BLE001
        return f"docker probe failed: {type(exc).__name__}: {exc}"


def sandbox_preflight(mode: str = "local_dev") -> SandboxProbe:
    """Drive the sandbox and the tool executor directly, then report what happened."""
    p = SANDBOX
    p.mode = mode
    p.docker_available = _probe_docker()
    sandbox: SandboxRuntime = get_sandbox(mode)
    p.runtime_class = type(sandbox).__name__
    TRACE.add("", "sandbox", "sandbox.acquired",
              f"world.sandbox.get_sandbox({mode!r}) -> {p.runtime_class}",
              detail=(f"protocol methods: {', '.join(KERNEL_SURFACE['sandbox_methods'])}; "
                      f"{p.docker_available}"),
              rules=[f"S1 get_sandbox({mode!r}) selects "
                     f"{'DockerSandboxRuntime' if mode == 'docker' else 'LocalProcessRuntime'}",
                     "S2 LocalProcessRuntime documents itself as NOT secure isolation — "
                     "this run does not claim otherwise"])

    executor: ToolExecutor | None = None
    try:
        sandbox.start(CFG.repo_path)
        p.started = True

        # exec — a real subprocess, a real CommandResult
        p.exec_result = sandbox.exec(SANDBOX_PROBE_COMMAND, ".", 20)
        # read_file — bytes straight off the sandbox
        p.bytes_read = len(sandbox.read_file("pyproject.toml", 4096))


        # Background process lifetime: start -> poll -> list -> kill
        p.bg_started = sandbox.exec_background(SANDBOX_BG_COMMAND, ".")
        time.sleep(0.8)   # let the reader threads accumulate real output
        p.bg_polled = sandbox.read_process_output(p.bg_started.handle_id)
        p.listed = len(sandbox.list_processes())
        sandbox.kill_process(p.bg_started.handle_id)
        p.killed = not sandbox.read_process_output(p.bg_started.handle_id).is_running

        TRACE.add(
            "", "sandbox", "sandbox.exercised",
            f"Sandbox protocol driven directly — every method called",
            detail=(f"exec: exit={p.exec_result.exit_code} "
                    f"stdout={p.exec_result.stdout.strip()[:40]!r} "
                    f"({p.exec_result.duration_ms}ms); "
                    f"read_file: {p.bytes_read} bytes; "
                    f"exec_background: pid={p.bg_polled.pid} "
                    f"stdout_so_far={len(p.bg_polled.stdout_so_far)}B; "
                    f"list_processes: {p.listed}; killed={p.killed}"),
            rules=["S3 exec returns contracts.tool.CommandResult — a real exit code, "
                   "not a simulated one",
                   "S4 exec_background returns contracts.process.BackgroundProcess; the "
                   "command is unbuffered (python -u + flush) so the reader threads see "
                   "output promptly instead of it sitting in a pipe buffer",
                   "S5 kill_process then read_process_output confirms is_running went False"],
            meta={"exit_code": p.exec_result.exit_code, "pid": p.bg_polled.pid,
                  "killed": p.killed})

        # ToolExecutor — the same class control.loop uses, driven with real actions
        executor = ToolExecutor(sandbox, CFG.repo_path)
        for tool, params in (("list_tree", {"max_depth": 1}),
                            ("path_exists", {"path": "pyproject.toml"}),
                            ("check_port", {"port": CFG.port, "host": "127.0.0.1"}),
                            ("search_files", {"pattern": "*.py", "glob": "src/**/*"})):
            raw = executor.execute({"tool": tool, "params": params})
            try:
                p.tool_results[tool] = ToolResult.model_validate(raw)
            except Exception:  # noqa: BLE001 — flat envelopes (check_port) are not ToolResult
                p.tool_results[tool] = ToolResult(ok=bool(raw.get("ok")),
                                                  data=raw.get("data"),
                                                  error=raw.get("error"),
                                                  meta=raw.get("meta") or {})


        TRACE.add(
            "", "sandbox", "sandbox.tools",
            f"ToolExecutor drove {len(p.tool_results)} tools against this sandbox",
            detail="; ".join(
                f"{t}: ok={r.ok}"
                + (f" keys={sorted(r.data)[:4]}" if isinstance(r.data, dict) else "")
                for t, r in p.tool_results.items()),
            rules=["S6 ToolExecutor.execute takes the same {'tool','params'} action dict "
                   "control.loop._resolve_tool_action produces — no separate code path",
                   "S7 each envelope is parsed back as contracts.tool.ToolResult, which "
                   "is how the loop's observations are shaped"],
            meta={t: r.ok for t, r in p.tool_results.items()})
    except Exception as exc:  # noqa: BLE001 — a preflight failure is reported, not fatal
        p.errors.append(f"{type(exc).__name__}: {exc}")
        TRACE.add("", "sandbox", "sandbox.error", f"Sandbox preflight failed: {exc}",
                  rules=["S8 the preflight is additive: the kernel builds its own "
                         "sandbox per investigation regardless of this outcome"])
    finally:
        try:
            sandbox.stop()
        except Exception as exc:  # noqa: BLE001
            p.errors.append(f"stop: {exc}")
    return p


def repository_precheck() -> dict:
    """world.repository.validate + world.scanner.scan, called directly, so the
    manifest the Planner will receive is visible before the run starts."""
    out: dict[str, Any] = {}
    try:
        kernel_repository.validate(CFG.repo_path)
        out["valid"] = True
    except Exception as exc:  # noqa: BLE001
        out["valid"] = False
        out["error"] = f"{type(exc).__name__}: {exc}"
        return out
    manifest = kernel_scanner.scan("inv_precheck", CFG.repo_path)
    out.update(files=manifest.total_files, dirs=manifest.total_dirs,
               key_files=list(manifest.key_files),
               top_extensions=dict(sorted(manifest.extensions.items(),
                                          key=lambda kv: -kv[1])[:6]),
               size_bytes=manifest.size_bytes_approx,
               max_depth=kernel_scanner._MAX_DEPTH)
    TRACE.add("", "sandbox", "repo.scanned",
              f"world.scanner.scan: {manifest.total_files} files / "
              f"{manifest.total_dirs} dirs",
              detail=f"key_files={list(manifest.key_files)}; "
                     f"extensions={out['top_extensions']}",
              rules=["S9 world.repository.validate accepted the path",
                     f"S10 scanner walks to depth {kernel_scanner._MAX_DEPTH} "
                     f"(_MAX_DEPTH) — the same manifest the kernel will build"])
    return out



# ══════════════════════════════════════════════════════════════════════════════
#  Node construction — real InvestigationNode / Hypothesis / ClaimTemplate
# ══════════════════════════════════════════════════════════════════════════════
# Building the kernel's own models (rather than dicts that resemble them) means
# Pydantic rejects a malformed plan here, at construction, instead of the kernel
# rejecting it over HTTP later.
#
# node.action is {"tool", "params"} — what ToolExecutor reads and what
# loop._resolve_tool_action falls back to. ToolRequest uses "parameters".
#
# Each hypothesis kind is paired with a tool whose payload it can actually read,
# verified against control.hypothesis.evaluate and world.tools:
#   execute_command -> exit_code_in     payload["exit_code"]   (flat)
#                   -> stdout_contains  payload["stdout"]      (flat)
#   path_exists     -> file_exists      payload["exists"]      (flat)
#   check_port      -> http_status      payload["status_code"] (200 live / 0 dead)
#   start_process   -> manual_escalate  always "unexpected" -> planner.interpret
#   read_file       -> json_path_equals evaluate() reads payload["resolved_value"],
#                      which read_file never sets, so this escalates too — the
#                      designed route for a hypothesis the evaluator cannot decide
#   everything else -> always_success   the envelope itself is the evidence

def mknode(nid: str, ntype: NodeType, tool: str, params: dict, hyp: Hypothesis, *,
           success: tuple[str, str, Any] | None = None,
           failure: tuple[str, str, Any] | None = None,
           depends_on: list[str] | None = None,
           goal_id: str | None = None,
           escalate_when: str | None = None) -> InvestigationNode:
    kwargs: dict[str, Any] = {
        "id": nid, "type": ntype, "action": {"tool": tool, "params": params},
        "hypothesis": hyp, "depends_on": list(depends_on or ()),
    }
    if success:
        kwargs["on_success"] = ClaimTemplate(claim_type=success[0], key=success[1],
                                            value=success[2])
    if failure:
        kwargs["on_failure"] = ClaimTemplate(claim_type=failure[0], key=failure[1],
                                            value=failure[2])
    if goal_id:
        kwargs["goal_id"] = goal_id
    if escalate_when:
        kwargs["escalate_when"] = escalate_when
    return InvestigationNode(**kwargs)


STDOUT_PROBE = "WIZARD-STDOUT-PROBE-4F81"

H_ALWAYS = Hypothesis(kind=HypothesisKind.always_success)
H_ESCALATE = Hypothesis(kind=HypothesisKind.manual_escalate)
H_EXIT0 = Hypothesis(kind=HypothesisKind.exit_code_in,
                     success_values=[0], failure_values=[1, 2, 127, 128])
H_EXISTS = Hypothesis(kind=HypothesisKind.file_exists)
H_PORT = Hypothesis(kind=HypothesisKind.http_status,
                    success_values=[200], failure_values=[0])
H_STDOUT = Hypothesis(kind=HypothesisKind.stdout_contains, pattern=STDOUT_PROBE)
H_JSONPATH = Hypothesis(kind=HypothesisKind.json_path_equals,
                        json_path="project.name", success_values=["wizard-kernel"])



# ══════════════════════════════════════════════════════════════════════════════
#  The four phases
# ══════════════════════════════════════════════════════════════════════════════
# CHAIN DISCIPLINE. control.priority.next_ready only releases a node once every id
# in depends_on is in completed_ids — and loop adds a node to completed_ids whether
# it completed or failed (loop.py:246, 341-346), so an escalating node does not
# strand its dependents. The spine is still built only from nodes that end in
# expected_success, because a chain hanging off a failure is a chain whose evidence
# is unclear. Nodes that are *meant* to fail are leaves: they depend on the chain,
# nothing depends on them.
#
# next_ready breaks score ties with max(), which keeps the first-inserted node, so
# execution order is total and reproducible rather than incidental.

A_LAST = "a5_read_build_plan"
B_LAST = "b4_port_open"
C_LAST = "c4_kill_process"
D_LAST = "d12_navigate_kernel_api"

# Unbuffered so the sandbox's reader threads see output promptly. A buffered child
# would make read_process look empty and the evidence thin.
PROC_COMMAND = (
    'python -u -c "import time'
    ";[(print('wizard-bg tick',i,flush=True),time.sleep(0.3)) for i in range(80)]\""
)


def phase_a_nodes() -> list[InvestigationNode]:
    """Filesystem and configuration surface. Evidence tier: config_parse."""
    return [
        # ── spine ──────────────────────────────────────────────────────────────
        mknode("a1_map_tree", "discovery", "list_tree", {}, H_ALWAYS,
               success=("FS_TREE", "repository_tree_mapped", True)),
        mknode("a2_manifest_present", "verify", "path_exists",
               {"path": "pyproject.toml"}, H_EXISTS, depends_on=["a1_map_tree"],
               success=("FS_MANIFEST_FILE", "pyproject_toml_present", True),
               failure=("FS_MANIFEST_FILE", "pyproject_toml_present", False)),
        # read_file on pyproject.toml is also what feeds belief.extractors'
        # file_content extractor, which is where the PACKAGE and RUNTIME claims
        # come from — this module never authors those, the kernel does.
        mknode("a3_read_manifest", "read", "read_file",
               {"path": "pyproject.toml", "max_bytes": 65536}, H_ALWAYS,
               depends_on=["a2_manifest_present"],
               success=("FILE_READ", "pyproject.toml", True)),
        mknode("a4_index_sources", "discovery", "search_files",
               {"pattern": "*.py"}, H_ALWAYS, depends_on=["a3_read_manifest"],
               success=("FS_INDEX", "python_sources_indexed", True)),
        mknode(A_LAST, "read", "read_file",
               {"path": "BUILD_PLAN.md", "max_bytes": 65536}, H_ALWAYS,
               depends_on=["a4_index_sources"],
               success=("FS_DOC", "build_plan_read", True)),


        # ── leaves ─────────────────────────────────────────────────────────────
        # json_path_equals against a ToolResult envelope: evaluate() looks for
        # payload["resolved_value"], which read_file does not set, and read_file
        # only json-parses files ending .json — so a .toml path is doubly
        # unresolvable here. It escalates to planner.interpret, which is the
        # designed route. A distinct max_bytes keeps its validator fingerprint
        # different from a3's, since non-browser dedup is global per investigation.
        mknode("a3b_json_path_probe", "parse", "read_file",
               {"path": "pyproject.toml", "max_bytes": 32768}, H_JSONPATH,
               depends_on=["a3_read_manifest"],
               escalate_when="json_path unresolvable from a ToolResult envelope"),
        # Negative control: a path that must NOT exist, so file_exists resolves to
        # expected_failure and the on_failure claim is admitted as *contradicting*
        # evidence. Proves the runtime records disconfirmation, not only support.
        mknode("a6_absent_path_probe", "verify", "path_exists",
               {"path": "docs/this-path-must-not-exist.md"}, H_EXISTS,
               depends_on=[A_LAST],
               success=("FS_ABSENT", "phantom_path_present", True),
               failure=("FS_ABSENT", "phantom_path_present", False)),
    ]


def phase_b_nodes() -> list[InvestigationNode]:
    """Execution surface. Evidence tier: execution — the strongest the kernel has."""
    return [
        # ── spine ──────────────────────────────────────────────────────────────
        mknode("b1_stdout_probe", "execute", "execute_command",
               {"command": f'python -c "print(\'{STDOUT_PROBE}\')"'}, H_STDOUT,
               depends_on=[A_LAST],
               success=("EXEC_STDOUT", "stdout_pattern_matched", True),
               failure=("EXEC_STDOUT", "stdout_pattern_matched", False)),
        mknode("b2_interpreter", "execute", "execute_command",
               {"command": "python --version"}, H_EXIT0, depends_on=["b1_stdout_probe"],
               success=("EXEC_INTERPRETER", "python_interpreter_runs", True),
               failure=("EXEC_INTERPRETER", "python_interpreter_runs", False)),
        mknode("b3_packager", "execute", "execute_command",
               {"command": "python -m pip --version"}, H_EXIT0,
               depends_on=["b2_interpreter"],
               success=("EXEC_PACKAGER", "pip_module_runs", True),
               failure=("EXEC_PACKAGER", "pip_module_runs", False)),
        # check_port against this very server: the kernel probing its own liveness.
        # Feeds the port_check extractor's RUNTIME claim at execution tier.
        mknode(B_LAST, "verify", "check_port",
               {"port": CFG.port, "host": "127.0.0.1"}, H_PORT,
               depends_on=["b3_packager"],
               success=("PORT_OPEN", f"kernel_api_port_{CFG.port}", True),
               failure=("PORT_OPEN", f"kernel_api_port_{CFG.port}", False)),


        # ── leaves ─────────────────────────────────────────────────────────────
        # Port 9 (discard) is reserved and never listens: the second negative
        # control, and the one that exercises http_status' failure_values branch.
        mknode("b5_port_closed_control", "verify", "check_port",
               {"port": 9, "host": "127.0.0.1"}, H_PORT, depends_on=[B_LAST],
               success=("PORT_CLOSED", "discard_port_9_listening", True),
               failure=("PORT_CLOSED", "discard_port_9_listening", False)),
        # A leaf because git's presence is an environment fact, not something the
        # run should hinge on. If git is missing this node fails alone.
        mknode("b6_vcs", "execute", "execute_command",
               {"command": "git rev-parse --abbrev-ref HEAD"}, H_EXIT0,
               depends_on=[B_LAST],
               success=("EXEC_VCS", "git_branch_resolved", True),
               failure=("EXEC_VCS", "git_branch_resolved", False)),
    ]


def phase_c_nodes() -> list[InvestigationNode]:
    """Background process. A leaf: its handle_id is minted by the sandbox at
    runtime, so no static plan can name it. manual_escalate routes the real
    observation to planner.interpret, which reads the handle and emits the rest."""
    return [
        mknode("c1_start_process", "execute", "start_process",
               {"command": PROC_COMMAND}, H_ESCALATE, depends_on=[B_LAST],
               escalate_when="handle_id is runtime-minted: escalate to planner.interpret"),
    ]


def phase_c_followups(handle_id: str) -> list[InvestigationNode]:
    """Emitted by /plan/interpret once the real handle_id has been observed. The
    first node has no depends_on: c1 is already spent, and although completed_ids
    does include failed nodes, chaining onto an escalation would tie this lifetime
    to a node whose evidence was inconclusive."""
    return [
        mknode("c2_read_process", "execute", "read_process", {"handle_id": handle_id},
               H_ALWAYS, success=("PROC_READ", "background_output_observed", True)),
        mknode("c3_list_processes", "discovery", "list_processes", {}, H_ALWAYS,
               depends_on=["c2_read_process"],
               success=("PROC_LIST", "process_table_observed", True)),
        mknode(C_LAST, "execute", "kill_process", {"handle_id": handle_id}, H_ALWAYS,
               depends_on=["c3_list_processes"],
               success=("PROC_KILL", "background_process_terminated", True)),
    ]



def phase_d_nodes() -> list[InvestigationNode]:
    """Browser surface. Every registered browser verb, plus one navigation the
    egress policy must refuse."""
    base = CFG.base
    return [
        # ── spine ──────────────────────────────────────────────────────────────
        mknode("d1_navigate_home", "execute", "browser_navigate",
               {"url": f"{base}/flow/fixtures/home"}, H_ALWAYS, depends_on=[C_LAST],
               success=("WEB_NAV", "fixture_home_reached", True)),
        mknode("d2_snapshot_home", "parse", "browser_snapshot", {}, H_ALWAYS,
               depends_on=["d1_navigate_home"],
               success=("WEB_SNAPSHOT", "home_accessibility_tree", True)),
        mknode("d3_click_detail", "execute", "browser_click", {"selector": "#to-detail"},
               H_ALWAYS, depends_on=["d2_snapshot_home"],
               success=("WEB_CLICK", "followed_detail_link", True)),
        mknode("d4_extract_detail", "parse", "browser_extract", {}, H_ALWAYS,
               depends_on=["d3_click_detail"],
               success=("WEB_EXTRACT", "detail_text_extracted", True)),
        mknode("d5_history_back", "execute", "browser_back", {}, H_ALWAYS,
               depends_on=["d4_extract_detail"],
               success=("WEB_BACK", "history_back_confirmed", True)),
        mknode("d7_navigate_form", "execute", "browser_navigate",
               {"url": f"{base}/flow/fixtures/form"}, H_ALWAYS,
               depends_on=["d5_history_back"],
               success=("WEB_NAV", "fixture_form_reached", True)),
        mknode("d8_type_query", "execute", "browser_type",
               {"selector": "#query", "text": FORM_QUERY}, H_ALWAYS,
               depends_on=["d7_navigate_form"],
               success=("WEB_TYPE", "search_field_filled", True)),
        mknode("d9_submit_form", "execute", "browser_click", {"selector": "#submit"},
               H_ALWAYS, depends_on=["d8_type_query"],
               success=("WEB_CLICK", "form_submitted", True)),
        mknode("d10_snapshot_result", "parse", "browser_snapshot", {}, H_ALWAYS,
               depends_on=["d9_submit_form"],
               success=("WEB_SNAPSHOT", "result_accessibility_tree", True)),
        mknode("d11_extract_result", "parse", "browser_extract", {}, H_ALWAYS,
               depends_on=["d10_snapshot_result"],
               success=("WEB_EXTRACT", "result_text_extracted", True)),
        # The kernel reading its own live API surface through the agent's browser.
        mknode(D_LAST, "execute", "browser_navigate",
               {"url": f"{base}/v1/investigations"}, H_ALWAYS,
               depends_on=["d11_extract_result"],
               success=("WEB_SELF", "kernel_api_surface_rendered", True)),

        # ── leaf ───────────────────────────────────────────────────────────────
        # 127.0.0.1/localhost is the whole allowlist, so the validator's
        # _validate_url must refuse this before Chromium is asked to do anything.
        # Both the Explorer's request and the kernel's fallback are rejected — the
        # intended outcome, and why this is a leaf.
        mknode("d13_blocked_egress", "execute", "browser_navigate",
               {"url": "https://example.org/must-be-blocked"}, H_ALWAYS,
               depends_on=[D_LAST],
               success=("WEB_EGRESS", "offsite_navigation_allowed", True)),
    ]



# ── Goals ─────────────────────────────────────────────────────────────────────
# GoalEngine.evaluate_all needs at least one claim of EVERY required type at or
# above belief_threshold, so a goal spanning a whole phase can only close once that
# phase has finished. That is what stops the loop breaking early on
# goals.all_satisfied() and skipping later phases.
#
# The PACKAGE / RUNTIME / EXECUTION / FILESYSTEM goals require claim types this
# module never authors — they come from belief.extractors reading real observations.
# Requiring them is how the run proves the extraction path works end to end.
#
# Trust arithmetic is the kernel's, computed by expected_belief() rather than
# restated: execution 0.909, config_parse 0.857, documentation 0.667. All clear the
# 0.6 default threshold; a contradict-only claim scores 0.0, which is why both
# negative controls sit outside every goal's required set.

GOALS_BASE: list[GoalDefinition] = [
    GoalDefinition(name="Repository Surface Mapped",
                   required_claim_types=["FS_TREE", "FS_MANIFEST_FILE", "FILE_READ",
                                        "FS_INDEX", "FS_DOC"]),
    GoalDefinition(name="Dependency Manifest Parsed",
                   required_claim_types=["PACKAGE"]),
    GoalDefinition(name="Filesystem Facts Extracted",
                   required_claim_types=["FILESYSTEM"]),
    GoalDefinition(name="Execution Plane Verified",
                   required_claim_types=["EXEC_STDOUT", "EXEC_INTERPRETER",
                                        "EXEC_PACKAGER", "PORT_OPEN"],
                   requires_execution_evidence=True),
    GoalDefinition(name="Command Exit Codes Observed",
                   required_claim_types=["EXECUTION"],
                   requires_execution_evidence=True),
    GoalDefinition(name="Runtime Identified And Port Live",
                   required_claim_types=["RUNTIME"],
                   requires_execution_evidence=True),
    GoalDefinition(name="Background Process Lifecycle Verified",
                   required_claim_types=["PROC_READ", "PROC_LIST", "PROC_KILL"]),
]

GOAL_WEB = GoalDefinition(
    name="Browser Action Surface Exercised",
    required_claim_types=["WEB_NAV", "WEB_SNAPSHOT", "WEB_CLICK", "WEB_EXTRACT",
                         "WEB_BACK", "WEB_TYPE", "WEB_SELF", "WEB"],
    requires_execution_evidence=True)


@dataclass
class Phase:
    name: str
    gate_claim_type: str | None
    terminal_claim_type: str
    emit: Any
    browser_only: bool = False


PHASES: list[Phase] = [
    Phase("B execution", "FS_DOC", "PORT_OPEN", phase_b_nodes),
    Phase("C background-process", "PORT_OPEN", "PROC_KILL", phase_c_nodes),
    Phase("D browser", "PROC_KILL", "WEB_SELF", phase_d_nodes, browser_only=True),
]



# ══════════════════════════════════════════════════════════════════════════════
#  Per-investigation planner / explorer state
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class PlanState:
    inv_id: str
    browser: bool
    allowed_domains: list[str]
    emitted: set[str] = field(default_factory=set)
    interpreted: set[str] = field(default_factory=set)
    # A mirror of the kernel's validator: same class, same arguments. The Explorer
    # runs its request through this BEFORE answering, so the trace records the
    # verdict the kernel is about to reach. Each request passes through exactly one
    # mirror call and one kernel call, so the two dedup fingerprint sets stay in
    # lockstep and the mirror never invents a duplicate the kernel would not see.
    validator: ToolRequestValidator | None = None
    mirror_rejections: int = 0
    mirror_checks: int = 0

    def ensure_validator(self) -> ToolRequestValidator:
        if self.validator is None:
            self.validator = ToolRequestValidator(
                workspace_root=CFG.repo_path, allowed_domains=self.allowed_domains)
        return self.validator

    def as_dict(self) -> dict:
        return {"inv_id": self.inv_id, "browser": self.browser,
                "allowed_domains": self.allowed_domains,
                "phases_emitted": sorted(self.emitted),
                "interpreted_nodes": sorted(self.interpreted),
                "mirror_checks": self.mirror_checks,
                "mirror_rejections": self.mirror_rejections}


class PlanRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._states: dict[str, PlanState] = {}

    def open(self, inv_id: str, browser: bool, allowed_domains: list[str]) -> PlanState:
        with self._lock:
            st = PlanState(inv_id=inv_id, browser=browser,
                           allowed_domains=list(allowed_domains))
            self._states[inv_id] = st
            return st

    def get(self, inv_id: str) -> PlanState | None:
        with self._lock:
            return self._states.get(inv_id)

    def all(self) -> list[PlanState]:
        with self._lock:
            return list(self._states.values())


PLANS = PlanRegistry()


def _high_trust_types(kg_summary: dict) -> set[str]:
    """kg_summary.high_trust_claims is what context.packager exposes at or above its
    verified threshold. The Planner sees nothing else about trust (invariant 3)."""
    return {c.get("type") for c in (kg_summary or {}).get("high_trust_claims", []) or []}



# ══════════════════════════════════════════════════════════════════════════════
#  SERVICE 1 — Investigation Planner
# ══════════════════════════════════════════════════════════════════════════════
# Every handler is a sync `def` on purpose: FastAPI runs those in its threadpool.
# The kernel's loop thread is blocked on httpx calling back into this same server,
# so an `async def` handler would need the event loop the loop thread is not on.

planner_router = APIRouter(prefix="/plan", tags=["flow-planner"])


@planner_router.post("/initial")
def plan_initial(body: dict) -> dict:
    """Kernel -> Planner, once, right after world.scanner.scan.

    In : {manifest: RepositoryManifest, intent, targets}
    Out: contracts.plan.TechnologyPlan
    """
    manifest = RepositoryManifest.model_validate(body.get("manifest") or {})
    intent = str(body.get("intent", ""))
    targets = list(body.get("targets") or [])
    browser = TARGET_BROWSER in targets

    # allowed_domains is not in this packet, so the mirror validator is configured
    # from the same policy the driver POSTed for this session's role.
    allowed = ["127.0.0.1", "localhost"] if browser else []
    st = PLANS.open(manifest.investigation_id, browser, allowed)

    rules: list[str] = []
    signals: list[str] = []
    if "pyproject.toml" in manifest.key_files:
        rules.append("R1 manifest: key_files contains pyproject.toml -> Python project")
        signals.append("pyproject.toml")
    py_count = manifest.extensions.get(".py", 0)
    if py_count:
        rules.append(f"R2 extensions: {py_count} *.py files -> Python source tree")
        signals.append(f"{py_count} .py files")
    rules.append(f"R3 targets: {TARGET_BROWSER!r} "
                 + ("present -> browser phase D is in play" if browser
                    else "absent -> phases A-C only"))
    rules.append("R4 evidence tiers: "
                 + ", ".join(f"{t}={expected_belief(t)}"
                             for t in KERNEL_SURFACE["source_tiers"])
                 + f" (belief for one supporting observation, U0={kernel_trust.U0}); "
                   f"every tier this plan relies on clears the 0.6 default threshold")

    goals = list(GOALS_BASE) + ([GOAL_WEB] if browser else [])
    seed = phase_a_nodes()
    st.emitted.add("A filesystem")

    plan = TechnologyPlan(
        technologies=[TechnologyEntry(
            name="Python", confidence="high" if signals else "low",
            signals=signals or ["no manifest signal — generic discovery"],
            initial_goals=goals,
            priority_files=[f for f in ("pyproject.toml", "BUILD_PLAN.md")
                            if f in manifest.key_files] or ["pyproject.toml"],
        )],
        seed_nodes=seed,
    )


    TRACE.add(
        manifest.investigation_id, "planner", "planner.initial",
        f"Initial plan: {len(goals)} goals, {len(seed)} seed nodes",
        detail=(f"scan: {manifest.total_files} files / {manifest.total_dirs} dirs "
                f"(~{manifest.size_bytes_approx} bytes), key_files={manifest.key_files}; "
                f"intent={intent!r}; phases: A now + "
                f"{len(PHASES) if browser else len(PHASES) - 1} evidence-gated"),
        rules=rules,
        meta={"goals": [g.name for g in goals], "seed_nodes": [n.id for n in seed],
              "browser": browser,
              "required_claim_types": sorted({t for g in goals
                                              for t in g.required_claim_types})},
    )
    _think()
    return plan.model_dump(mode="json")


@planner_router.post("/next")
def plan_next(body: dict) -> dict:
    """Kernel -> Planner when the graph runs dry, or when the Verifier reports gaps.

    In : {investigation_id, reason, kg_summary, missing_evidence, [weak_claims]}
    Out: {"new_nodes": [InvestigationNode, ...]} — an empty list ends the loop
    """
    inv_id = str(body.get("investigation_id", ""))
    reason = str(body.get("reason", ""))
    kg_summary = body.get("kg_summary") or {}
    missing = list(body.get("missing_evidence") or [])
    weak = list(body.get("weak_claims") or [])
    present = _high_trust_types(kg_summary)
    st = PLANS.get(inv_id)

    if st is None:
        TRACE.add(inv_id, "planner", "planner.next",
                  "No plan state for this investigation — returning no nodes",
                  detail="/plan/initial was never seen for this id",
                  rules=["R0 unknown session -> return [] so the loop terminates "
                         "cleanly rather than guessing"])
        return {"new_nodes": []}

    for phase in PHASES:
        if phase.name in st.emitted:
            continue
        if phase.browser_only and not st.browser:
            st.emitted.add(phase.name)
            TRACE.add(inv_id, "planner", "planner.gated",
                      f"Phase {phase.name} skipped — this session has no browser plane",
                      rules=[f"R3 targets lacked {TARGET_BROWSER!r}"])
            continue


        if phase.gate_claim_type and phase.gate_claim_type not in present:
            TRACE.add(
                inv_id, "planner", "planner.gated",
                f"Phase {phase.name} withheld — gate {phase.gate_claim_type} "
                f"not yet believed",
                detail=(f"reason={reason}; believed types now = "
                        f"{sorted(t for t in present if t)}"
                        + (f"; kernel reports missing: {missing[:3]}" if missing else "")),
                rules=[f"R5 gate: release {phase.name} only once "
                       f"{phase.gate_claim_type} appears in "
                       f"kg_summary.high_trust_claims — progression is driven by "
                       f"admitted evidence, not by a step counter"],
                meta={"gate": phase.gate_claim_type, "reason": reason,
                      "weak_claims": weak[:5]},
            )
            return {"new_nodes": []}

        nodes = phase.emit()
        st.emitted.add(phase.name)
        spine = [n.id for n in nodes
                 if n.hypothesis.kind != HypothesisKind.manual_escalate]
        TRACE.add(
            inv_id, "planner", "planner.next",
            f"Phase {phase.name} released: {len(nodes)} nodes",
            detail=(f"reason={reason}; gate {phase.gate_claim_type} satisfied; "
                    f"terminal claim = {phase.terminal_claim_type}; "
                    f"tools = {sorted({n.action['tool'] for n in nodes})}"),
            rules=[f"R5 gate {phase.gate_claim_type} believed -> release {phase.name}",
                   "R6 chain: the phase spine depends on the previous phase's terminal "
                   "node; nodes designed to fail or escalate are leaves, so a "
                   "deliberate failure never sits between two nodes that must run"],
            meta={"nodes": [n.id for n in nodes], "spine": spine, "reason": reason},
        )
        _think()
        return {"new_nodes": [n.model_dump(mode="json") for n in nodes]}

    TRACE.add(inv_id, "planner", "planner.next",
              "All phases delivered — no further nodes",
              detail=f"reason={reason}; the loop will now finalise and report",
              rules=["R7 exhaustion: every phase emitted -> return [] so the loop ends "
                     "(budget would terminate it regardless — invariant 7)"])
    return {"new_nodes": []}



@planner_router.post("/interpret")
def plan_interpret(body: dict) -> dict:
    """Kernel -> Planner when a node's outcome is `unexpected` (MatchResult).

    Two real uses here, both needing a value only the live run can supply:
      start_process -> read the sandbox-minted handle_id out of the observation and
                       emit the process lifetime against it
      read_file     -> the json_path hypothesis is unevaluable against a ToolResult
                       envelope, so resolve it here from the real payload
    """
    node = InvestigationNode.model_validate(body.get("node") or {})
    obs = Observation.model_validate(body.get("observation") or {})
    inv_id = obs.investigation_id
    st = PLANS.get(inv_id)

    # Cross-check: confirm independently that this really was `unexpected`. Calling
    # the kernel's own evaluator on values already in hand — a pure function, no
    # state written (invariant 3 intact).
    outcome: MatchResult = kernel_hypothesis.evaluate(node, obs)

    # The payload is a ToolResult envelope for most tools; execute_command uses the
    # flat CommandResult shape. Parse whichever it is rather than assuming.
    envelope: ToolResult | None = None
    try:
        envelope = ToolResult.model_validate(obs.payload)
    except Exception:  # noqa: BLE001 — flat envelope; fall back to raw keys
        envelope = None
    data = (envelope.data if envelope and isinstance(envelope.data, dict)
            else obs.payload.get("data") or {})
    meta = (envelope.meta if envelope else obs.payload.get("meta")) or {}

    guard = f"{node.id}:{obs.source_tool}"
    if st is not None:
        if guard in st.interpreted:
            return {"new_nodes": []}
        st.interpreted.add(guard)


    # ── start_process: mint the process lifetime from the real handle ──────────
    if obs.source_tool == "start_process":
        handle = meta.get("handle_id") or data.get("handle_id")
        if not handle:
            TRACE.add(inv_id, "planner", "planner.interpret",
                      f"{node.id} escalated but carried no handle_id",
                      detail=f"meta={meta}, data keys={sorted(data)}",
                      rules=["R8 interpret: no handle -> no follow-up is derivable"])
            return {"new_nodes": []}

        detail = f"handle_id={handle}"
        try:
            # world.tools puts bg.model_dump() straight into data, so this is a real
            # BackgroundProcess round-trip, not a guess at its shape.
            bp = BackgroundProcess.model_validate(data)
            detail = (f"handle_id={handle}, pid={bp.pid}, running={bp.is_running}, "
                      f"cmd={bp.command[:40]!r}")
        except Exception:  # noqa: BLE001 — the handle is what matters, not the extras
            pass

        nodes = phase_c_followups(str(handle))
        TRACE.add(
            inv_id, "planner", "planner.interpret",
            f"Observed live process — emitting its lifetime ({len(nodes)} nodes)",
            detail=detail,
            rules=[f"R8 interpret: control.hypothesis.evaluate returned {outcome!r} for "
                   f"kind {node.hypothesis.kind.value}, which is how a runtime-only "
                   f"value reaches the Planner at all",
                   "R9 lifecycle: read_process -> list_processes -> kill_process, "
                   "chained, so the process is observed while alive and then torn down"],
            meta={"handle_id": handle, "nodes": [n.id for n in nodes],
                  "outcome": outcome},
        )
        _think()
        return {"new_nodes": [n.model_dump(mode="json") for n in nodes]}


    # ── read_file: resolve the json_path the evaluator could not ───────────────
    if obs.source_tool == "read_file" and node.hypothesis.json_path:
        parsed = data.get("parsed")
        content = data.get("content") or ""
        resolved: Any = parsed
        for part in node.hypothesis.json_path.split("."):
            resolved = resolved.get(part) if isinstance(resolved, dict) else None
        # read_file only json-parses paths ending .json, so a .toml file arrives with
        # parsed=None. That is real kernel behaviour, so read the name off the text
        # rather than pretending the path resolved.
        source = "data.parsed"
        if resolved is None and content:
            import re
            if m := re.search(r'^\s*name\s*=\s*["\']([^"\']+)["\']', content, re.M):
                resolved = m.group(1)
                source = "regex over data.content (read_file parses only *.json)"
        matched = resolved in (node.hypothesis.success_values or [])

        follow: list[InvestigationNode] = []
        if isinstance(resolved, str) and resolved:
            follow = [mknode("a3c_locate_package_name", "planner", "search_files",
                             {"pattern": f"{resolved}*", "glob": "**/*.toml"}, H_ALWAYS,
                             success=("PKG_NAME_LOCATED", f"package_name:{resolved}", True))]
        TRACE.add(
            inv_id, "planner", "planner.interpret",
            f"Resolved {node.hypothesis.json_path} = {resolved!r} "
            f"({'matches' if matched else 'differs from'} the hypothesis)",
            detail=f"source: {source}; emitting {len(follow)} follow-up node(s)",
            rules=[f"R10 interpret: evaluate() returned {outcome!r} because "
                   f"{node.hypothesis.kind.value} reads payload['resolved_value'], "
                   f"which read_file never sets — so the Planner resolves the path "
                   f"itself from the real observation",
                   "R11 the follow-up is a leaf: nothing in the spine waits on it"],
            meta={"json_path": node.hypothesis.json_path, "resolved": resolved,
                  "matched": matched, "outcome": outcome,
                  "nodes": [n.id for n in follow]},
        )
        _think()
        return {"new_nodes": [n.model_dump(mode="json") for n in follow]}

    TRACE.add(inv_id, "planner", "planner.interpret",
              f"Escalation from {node.id} produced no actionable follow-up",
              detail=f"source_tool={obs.source_tool!r}, obs_type={obs.obs_type!r}, "
                     f"outcome={outcome!r}",
              rules=["R8 interpret: only start_process and json_path escalations mint "
                     "follow-ups in this plan; anything else is reported and dropped"])
    return {"new_nodes": []}



# ══════════════════════════════════════════════════════════════════════════════
#  SERVICE 2 — Explorer Agent
# ══════════════════════════════════════════════════════════════════════════════
# Receives exactly the keys the kernel's context packager emits: investigation_id,
# intent, targets, current_node{id,type,action,goal_id}, active_goals, kg_summary,
# remaining_budget. No observations, no trust scores, no graph. The rules are a pure
# function of that packet, so the same packet always yields the same request — and
# the request is checked against the kernel's own validator before being returned,
# which is why loop._resolve_tool_action's node_plan fallback never has to fire.

explorer_router = APIRouter(prefix="/agent", tags=["flow-explorer"])


def _explorer_decide(ctx: dict, st: PlanState | None
                     ) -> tuple[ToolRequest, list[str], ValidationResult | None]:
    node_ctx = ctx.get("current_node") or {}
    action = node_ctx.get("action") or {}
    tool = str(action.get("tool", "list_tree"))
    params = dict(action.get("params") or {})
    budget = int(ctx.get("remaining_budget") or 0)
    kg = ctx.get("kg_summary") or {}
    present = _high_trust_types(kg)
    open_goals = ctx.get("active_goals") or []
    claims_n = kg.get("claims_count", 0)
    contradictions = kg.get("contradictions") or []

    rules: list[str] = [
        f"E1 respect-plan: node {node_ctx.get('id')} is typed "
        f"{node_ctx.get('type')!r}; keep tool {tool!r} — substituting a different tool "
        f"would strand the dependency chain the graph is walking",
    ]

    # E2 — spend breadth only while there is budget left to act on what it finds.
    if tool == "list_tree" and "max_depth" not in params:
        depth = 3 if budget >= 20 else 2
        params["max_depth"] = depth
        rules.append(f"E2 depth-from-budget: remaining_budget={budget} "
                     f"{'>=' if budget >= 20 else '<'} 20 -> max_depth={depth}")

    # E3 — narrow the index once the tree is mapped; re-walking it whole is waste.
    if tool == "search_files" and "glob" not in params:
        scoped = "FS_TREE" in present
        params["glob"] = "src/**/*" if scoped else "**/*"
        rules.append(f"E3 index-scope: FS_TREE "
                     f"{'believed -> restrict to src/**/*' if scoped else 'unknown -> full sweep'}")


    # E4 — honour the Planner's read width, but never exceed the tool's own default.
    if tool == "read_file":
        want = int(params.get("max_bytes", 65536))
        params["max_bytes"] = min(want, 65536)
        rules.append(f"E4 read-width: Planner asked max_bytes={want}, clamped to the "
                     f"tool default 65536 -> {params['max_bytes']} (distinct widths also "
                     f"keep validator fingerprints distinct, and non-browser dedup is "
                     f"global per investigation)")

    # E5 — state the egress expectation out loud before asking to navigate.
    if tool in _URL_TOOLS:
        url = str(params.get("url", ""))
        allow = st.allowed_domains if st else []
        rules.append(f"E5 egress-precheck: allowlist={allow or '[] (fail-closed)'} "
                     f"vs {url[:60]!r}")

    # E6 — name the evidence tier this action buys, from the kernel's own mapping.
    tier = kernel_trust.source_tier_for_tool(tool)
    obs_type = KERNEL_SURFACE["tool_to_obs_type"].get(tool, "command_result")
    has_extractor = obs_type in KERNEL_SURFACE["extractor_obs_types"]
    rules.append(f"E6 evidence-tier: source_tier_for_tool({tool!r}) = {tier!r}; one "
                 f"supporting observation scores {expected_belief(tier)} against a 0.6 "
                 f"threshold")
    rules.append(f"E7 extraction-path: obs_type {obs_type!r} "
                 + ("has a registered extractor, so this observation can yield claims "
                    "beyond the node's own template"
                    if has_extractor else
                    "has no registered extractor, so only the node's ClaimTemplate "
                    "will produce a claim"))

    # E8 — goal alignment and current evidence state.
    names = [str(g.get("name")) for g in open_goals]
    rules.append(f"E8 goal-alignment: {len(open_goals)} goal(s) open "
                 f"({', '.join(names[:3])}{' …' if len(names) > 3 else ''})"
                 + (f"; node attributed to {node_ctx.get('goal_id')}"
                    if node_ctx.get("goal_id") else "; unattributed"))
    rules.append(f"E9 evidence-state: {claims_n} claim(s) admitted, {len(present)} "
                 f"type(s) above threshold"
                 + (f", {len(contradictions)} contradiction(s)" if contradictions else ""))
    rules.append(f"E10 context-size: ~"
                 f"{estimate_tokens(json.dumps(ctx, default=str))} tokens in this packet "
                 f"(context.sections.estimate_tokens)")

    reason = (f"{tool} for {node_ctx.get('id')} | tier={tier} | budget={budget} "
              f"| believed_types={len(present)}")
    request = ToolRequest(tool=tool, parameters=params, reason=reason)


    # E11 — self-check with the kernel's own validator, before answering.
    verdict: ValidationResult | None = None
    if st is not None:
        st.mirror_checks += 1
        verdict = st.ensure_validator().validate(request, budget)
        if verdict.valid:
            rules.append("E11 self-check: ToolRequestValidator accepts this request "
                         "(same class, same workspace root, same allowlist the kernel "
                         "applies a moment later) — so the node_plan fallback will not fire")
        else:
            st.mirror_rejections += 1
            rules.append(f"E11 self-check: ToolRequestValidator REFUSES this request — "
                         f"{verdict.reason} Sending it anyway: the refusal is the "
                         f"evidence this node exists to produce.")
    return request, rules, verdict


@explorer_router.post("/explorer")
def agent_explorer(ctx: dict) -> dict:
    """In: the trust-stripped context packet. Out: contracts.agent.ExplorerResponse."""
    inv_id = str(ctx.get("investigation_id", ""))
    node_ctx = ctx.get("current_node") or {}
    st = PLANS.get(inv_id)
    request, rules, verdict = _explorer_decide(ctx, st)

    TRACE.add(
        inv_id, "explorer", "explorer.decision",
        f"{node_ctx.get('id')} -> {request.tool}",
        detail=json.dumps(request.parameters, default=str)[:400],
        rules=rules,
        meta={"node_id": node_ctx.get("id"), "tool": request.tool,
              "parameters": request.parameters,
              "remaining_budget": ctx.get("remaining_budget"),
              "validator_ok": None if verdict is None else verdict.valid,
              "validator_reason": "" if verdict is None else verdict.reason},
    )
    _think()
    return ExplorerResponse(investigation_id=inv_id,
                            tool_request=request).model_dump(mode="json")



# ══════════════════════════════════════════════════════════════════════════════
#  SERVICE 3 — Verifier Agent
# ══════════════════════════════════════════════════════════════════════════════
# Consulted every loop._VERIFIER_INTERVAL completed nodes. Sees only
# [{claim_id, type, key, value}] — the loop strips trust before sending
# (invariant 3). Advisory only: the kernel reads the assessment and decides for
# itself whether to ask the Planner for more work.
#
# Its checklist is deliberately its own, not derived from the Planner's phase table:
# an auditor that shares the plan's assumptions cannot detect a gap in them.

VERIFIER_EXPECTATIONS: dict[str, str] = {
    "FS_TREE": "repository tree walked",
    "FILESYSTEM": "filesystem facts extracted from a real observation",
    "FILE_READ": "a manifest file read",
    "PACKAGE": "package identity parsed out of that manifest",
    "EXECUTION": "a command's exit code observed",
    "EXEC_STDOUT": "a command's stdout matched against a pattern",
    "EXEC_INTERPRETER": "the interpreter proven to run",
    "RUNTIME": "a live port probed and a runtime identified",
    "PROC_READ": "a background process observed while running",
    "PROC_KILL": "that process torn down again",
}
VERIFIER_WEB_EXPECTATIONS: dict[str, str] = {
    "WEB_NAV": "a page navigated",
    "WEB_SNAPSHOT": "an accessibility tree captured",
    "WEB_CLICK": "an element clicked",
    "WEB_TYPE": "a field filled",
    "WEB_BACK": "history traversed",
    "WEB_EXTRACT": "page text extracted",
    "WEB_SELF": "the kernel's own API surface rendered",
}


@explorer_router.post("/verifier")
def agent_verifier(body: dict) -> dict:
    """In: {"claims": [{claim_id, type, key, value}]}. Out: VerifierAssessment."""
    claims = list(body.get("claims") or [])
    present: set[str] = set()
    weak: list[str] = []

    for c in claims:
        present.add(str(c.get("type", "")))
        if str(c.get("value", "")).strip().lower() in ("", "none", "false", "0"):
            weak.append(str(c.get("claim_id", "")))

    expected = dict(VERIFIER_EXPECTATIONS)
    # The browser plane is inferred from the evidence itself, not from configuration
    # this agent was never given.
    if any(t.startswith("WEB") for t in present):
        expected.update(VERIFIER_WEB_EXPECTATIONS)

    gaps = [t for t in expected if t not in present]
    verdict = "needs_more_work" if gaps else "overall_sufficient"


    rules = [
        f"V1 checklist: {len(expected)} evidence classes expected, {len(present)} "
        f"distinct type(s) present",
        f"V2 gap-scan: missing {gaps if gaps else 'nothing'}",
        f"V3 weak-scan: {len(weak)} claim(s) carry a falsy value — those are "
        f"disconfirmations the runtime recorded on purpose (the negative controls), "
        f"not defects",
        f"V4 no trust visible: the loop strips trust before consulting me "
        f"(invariant 3), so this verdict rests on claim identity alone",
        f"V5 verdict: {verdict}"
        + (" — advisory; the runtime decides whether to act on it" if gaps else ""),
    ]
    TRACE.add(
        "", "verifier", "verifier.assessment",
        f"{verdict} — reviewed {len(claims)} claim(s)",
        detail="; ".join(f"{t}: {expected[t]}" for t in gaps[:4]) or "all expectations met",
        rules=rules,
        meta={"claims_reviewed": len(claims), "gaps": gaps, "weak": len(weak),
              "present": sorted(t for t in present if t)},
    )
    _think()
    return VerifierAssessment(
        investigation_id="",
        assessment=verdict,
        weak_claims=weak[:20],
        recommended_additional_investigations=[f"{t}: {expected[t]}" for t in gaps],
    ).model_dump(mode="json")



# ══════════════════════════════════════════════════════════════════════════════
#  Browse fixtures — real pages, served by this same process
# ══════════════════════════════════════════════════════════════════════════════
# Real HTTP, real HTML, a real form round-trip, a real accessibility tree. Local, so
# the run is reproducible without internet and 127.0.0.1 can be the entire
# allowlist — which is what makes the blocked-egress node meaningful.

fixtures_router = APIRouter(prefix="/flow/fixtures", tags=["flow-fixtures"])

_CSS = """
  body { font: 15px/1.6 system-ui, "Segoe UI", sans-serif; margin: 0; background: #f6f8fa;
         color: #1f2328; }
  header { background: #0d1117; color: #e6edf3; padding: 18px 28px; }
  header h1 { margin: 0; font-size: 20px; }
  header p { margin: 4px 0 0; color: #8b949e; font-size: 13px; }
  main { padding: 26px 28px; max-width: 820px; }
  h2 { font-size: 17px; margin: 22px 0 8px; }
  a { color: #0969da; }
  .card { background: #fff; border: 1px solid #d0d7de; border-radius: 8px;
          padding: 16px 18px; margin: 14px 0; }
  label { display: block; font-weight: 600; margin-bottom: 6px; }
  input[type=text] { width: 100%; padding: 9px 11px; font-size: 15px;
                     border: 1px solid #d0d7de; border-radius: 6px; }
  button { margin-top: 12px; padding: 9px 18px; font-size: 15px; cursor: pointer;
           background: #1f883d; color: #fff; border: 0; border-radius: 6px; }
  code { background: #eff1f3; padding: 1px 5px; border-radius: 4px; }
"""


def _page(title: str, subtitle: str, body: str) -> HTMLResponse:
    return HTMLResponse(
        f"<!doctype html><html lang=en><head><meta charset=utf-8>"
        f"<title>{title}</title><style>{_CSS}</style></head><body>"
        f"<header><h1>{title}</h1><p>{subtitle}</p></header><main>{body}</main>"
        f"</body></html>")


@fixtures_router.get("/home", response_class=HTMLResponse)
def fixture_home() -> HTMLResponse:
    return _page("Wizard Fixture — Home",
                 "served by the very process the agent is investigating", """
        <div class="card">
          <h2>Investigation entry point</h2>
          <p>This page exists so a browser action has something real to act on. The
          agent arrives with <code>browser_navigate</code>, reads the accessibility tree
          with <code>browser_snapshot</code>, then follows the link below using
          <code>browser_click</code>.</p>
          <p><a id="to-detail" href="/flow/fixtures/detail">Open the detail page</a></p>
        </div>
        <div class="card">
          <h2>Other surfaces on this host</h2>
          <ul>
            <li><a href="/flow/fixtures/form">A form to fill in and submit</a></li>
            <li><a href="/v1/investigations">The kernel's own investigation list</a></li>
            <li><a href="/health">Kernel health</a></li>
          </ul>
        </div>""")


DETAIL_MARKER = "WIZARD-DETAIL-MARKER-7A31"
RESULT_MARKER = "WIZARD-RESULT-MARKER-B52C"
FORM_QUERY = "wizard-kernel"


@fixtures_router.get("/detail", response_class=HTMLResponse)
def fixture_detail() -> HTMLResponse:
    return _page("Wizard Fixture — Detail",
                 "reached by a real click, not a scripted navigation", f"""
        <div class="card">
          <h2>Marker</h2>
          <p>The text below is what <code>browser_extract</code> has to bring back for
          the click to count as verified. It appears on no other page, so the
          extracted text is proof of arrival rather than proof of a request.</p>
          <p><code>{DETAIL_MARKER}</code></p>
        </div>
        <div class="card">
          <h2>Back</h2>
          <p>The agent leaves this page with <code>browser_back</code>, which is a
          history operation — the home page it lands on is the one it already saw.</p>
          <p><a href="/flow/fixtures/home">Home</a></p>
        </div>""")


@fixtures_router.get("/form", response_class=HTMLResponse)
def fixture_form() -> HTMLResponse:
    return _page("Wizard Fixture — Form",
                 "browser_type writes here, browser_click submits it", f"""
        <div class="card">
          <h2>Query</h2>
          <form id="lookup" method="get" action="/flow/fixtures/result">
            <label for="query">Package name</label>
            <input type="text" id="query" name="query" placeholder="type a name"
                   autocomplete="off">
            <button type="submit" id="submit">Look it up</button>
          </form>
          <p>The agent types <code>{FORM_QUERY}</code> — the name it read out of
          <code>pyproject.toml</code> earlier in the same investigation — so the
          filesystem plane and the browser plane meet on one value.</p>
        </div>""")


@fixtures_router.get("/result", response_class=HTMLResponse)
def fixture_result(query: str = Query(default="")) -> HTMLResponse:
    echoed = query or "(nothing submitted)"
    matched = query.strip() == FORM_QUERY
    return _page("Wizard Fixture — Result",
                 "a real GET with a real query string", f"""
        <div class="card">
          <h2>Submitted value</h2>
          <p>The server received: <code>{echoed}</code></p>
          <p>Matches the manifest name: <code>{matched}</code></p>
        </div>
        <div class="card">
          <h2>Marker</h2>
          <p><code>{RESULT_MARKER}</code></p>
        </div>""")


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 7 — sessions and the flow driver
# ══════════════════════════════════════════════════════════════════════════════
# Sessions are created through the kernel's own HTTP API (POST /v1/investigations),
# not by calling InvestigationManager in-process. That is deliberate: the same
# request body a CLI would send, the same 201, the same background loop thread, the
# same DELETE semantics. Three sessions run:
#
#   primary   — browser enabled, all four phases, the one the right pane shows
#   files     — no browser, phases A/B/C only; proves the plan is evidence-gated
#               rather than script-ordered, since phase D never unlocks for it
#   cancelled — created and DELETEd mid-flight, to exercise the cancel path and
#               show the loop honouring lifecycle state
#
# One browser per run: the screencast is a single CDP attachment and two concurrent
# Chromium sessions would make the right pane ambiguous about whose actions it shows.

PRIMARY_BUDGET = 56
FILES_BUDGET = 34
CANCEL_BUDGET = 34
TERMINAL_STATES = frozenset({
    LifecycleState.completed, LifecycleState.failed, LifecycleState.cancelled,
})


@dataclass
class Session:
    label: str
    role: str                      # primary | files | cancelled
    request: InvestigationRequest
    inv_id: str = ""
    created: bool = False
    deleted: bool = False
    final_state: str = ""
    status: dict = field(default_factory=dict)
    report: ReportResponse | None = None
    kernel_events: list[dict] = field(default_factory=list)
    error: str = ""

    def as_dict(self) -> dict:
        return {
            "label": self.label, "role": self.role, "inv_id": self.inv_id,
            "created": self.created, "deleted": self.deleted,
            "final_state": self.final_state, "status": self.status,
            "budget": self.request.options.budget,
            "browser_enabled": self.request.options.browser_enabled,
            "targets": self.request.targets,
            "has_report": self.report is not None,
            "kernel_event_count": len(self.kernel_events),
            "error": self.error,
        }


def _request_for(role: str) -> InvestigationRequest:
    """Real contract objects. The three agent URLs point back at this very process —
    that is the whole trick: the kernel talks to its planner/explorer/verifier over
    real HTTP, and the deterministic rule engines answering are mounted on the same
    uvicorn app."""
    base = CFG.base
    common = dict(
        planner_url=f"{base}/plan",
        agent_explorer_url=f"{base}/agent/explorer",
        agent_verifier_url=f"{base}/agent/verifier",
        sandbox_mode="local_dev",
    )
    if role == "primary":
        opts = InvestigationOptions(
            budget=PRIMARY_BUDGET, browser_enabled=True, browser_backend="local",
            # Fail-closed allowlist: only this host. d13_blocked_egress navigates
            # example.org and must be refused by the validator, not by Chromium.
            allowed_domains=[CFG.host, "localhost"], **common)
        return InvestigationRequest(repository_path=CFG.repo_path, intent="verify",
                                    targets=[TARGET_BROWSER, TARGET_FILES], options=opts)
    if role == "files":
        opts = InvestigationOptions(budget=FILES_BUDGET, browser_enabled=False, **common)
        return InvestigationRequest(repository_path=CFG.repo_path, intent="investigate",
                                    targets=[TARGET_FILES], options=opts)
    opts = InvestigationOptions(budget=CANCEL_BUDGET, browser_enabled=False, **common)
    return InvestigationRequest(repository_path=CFG.repo_path, intent="explain",
                                targets=[TARGET_FILES], options=opts)


class FlowRun:
    """Drives the whole demonstration on a background thread and keeps the state the
    dashboard polls. Holds no kernel state of its own — every field here is either a
    request it sent or a response the kernel gave back."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self.state: str = "idle"        # idle | preflight | running | done | failed
        self.sessions: list[Session] = []
        self.started_at: float = 0.0
        self.finished_at: float = 0.0
        self.error: str = ""
        self.terminal_report: str = ""
        self.precheck: dict = {}

    # ── lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Idempotent: a second call while running is a no-op, so the dashboard's
        start button and serve_live's conductor cannot race into two runs."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            if self.state in ("done", "failed"):
                return False
            self._thread = threading.Thread(target=self._drive, name="flow-driver",
                                            daemon=True)
            self.started_at = time.time()
            self.state = "preflight"
            self._thread.start()
            return True

    def join(self, timeout: float | None = None) -> None:
        t = self._thread
        if t is not None:
            t.join(timeout)

    def primary(self) -> Session | None:
        return next((s for s in self.sessions if s.role == "primary"), None)

    # ── the run ──────────────────────────────────────────────────────────────

    def _drive(self) -> None:
        try:
            self._preflight()
            self.state = "running"
            self._create_sessions()
            self._cancel_one()
            self._await_terminal()
            self._collect_reports()
            self.terminal_report = build_terminal_report(self)
            self.state = "done"
        except Exception as exc:  # noqa: BLE001 — the driver reports, it never dies silently
            self.error = f"{type(exc).__name__}: {exc}"
            self.state = "failed"
            TRACE.add("", "flow", "error", "flow driver failed", self.error)
            self.terminal_report = build_terminal_report(self)
        finally:
            self.finished_at = time.time()

    def _preflight(self) -> None:
        TRACE.add("", "flow", "phase", "preflight",
                  "sandbox and repository are checked before any investigation exists")
        probe = sandbox_preflight("local_dev")
        self.precheck = repository_precheck()
        TRACE.add("", "flow", "note", "preflight complete",
                  f"sandbox={probe.runtime_class} exec_ok={probe.exec_result is not None} "
                  f"files_visible={self.precheck.get('scan_file_count')}")

    def _create_sessions(self) -> None:
        for role, label in (("primary", "primary · browser + filesystem"),
                            ("files", "files · no browser"),
                            ("cancelled", "cancelled · deleted mid-flight")):
            s = Session(label=label, role=role, request=_request_for(role))
            self.sessions.append(s)
            _think()
            try:
                with httpx.Client(timeout=30.0) as c:
                    r = c.post(f"{CFG.base}/v1/investigations",
                               json=s.request.model_dump(mode="json"))
                r.raise_for_status()
                s.inv_id = r.json()["investigation_id"]
                s.created = True
                TRACE.add(s.inv_id, "flow", "session", f"session created: {role}",
                          f"POST /v1/investigations → 201 {s.inv_id} "
                          f"budget={s.request.options.budget} "
                          f"browser={s.request.options.browser_enabled}",
                          meta={"role": role, "targets": s.request.targets})
            except Exception as exc:  # noqa: BLE001
                s.error = f"{type(exc).__name__}: {exc}"
                TRACE.add("", "flow", "error", f"session create failed: {role}", s.error)

    def _cancel_one(self) -> None:
        """DELETE while the loop is genuinely mid-flight — the point is that the kernel
        stops on its own lifecycle check, not that we waited for it to finish."""
        s = next((x for x in self.sessions if x.role == "cancelled" and x.inv_id), None)
        if s is None:
            return
        time.sleep(1.2)
        try:
            with httpx.Client(timeout=30.0) as c:
                before = c.get(f"{CFG.base}/v1/investigations/{s.inv_id}").json()
                r = c.delete(f"{CFG.base}/v1/investigations/{s.inv_id}")
            r.raise_for_status()
            s.deleted = True
            TRACE.add(s.inv_id, "flow", "session", "session deleted mid-flight",
                      f"DELETE /v1/investigations/{s.inv_id} → {r.json().get('status')} "
                      f"(was {before.get('status')} after "
                      f"{before.get('nodes_completed')} nodes, "
                      f"{before.get('claims_count')} claims)")
        except Exception as exc:  # noqa: BLE001
            s.error = f"{type(exc).__name__}: {exc}"
            TRACE.add(s.inv_id, "flow", "error", "delete failed", s.error)

    def _await_terminal(self) -> None:
        """Poll the kernel's own status endpoint until every session is terminal or the
        deadline passes. LifecycleState is the authority — this never infers
        completion from the trace."""
        deadline = time.time() + CFG.poll_timeout_s
        live = [s for s in self.sessions if s.created]
        seen_seq: dict[str, int] = {s.inv_id: 0 for s in live}
        while time.time() < deadline:
            pending = [s for s in live if s.final_state not in TERMINAL_STATES]
            if not pending:
                break
            with httpx.Client(timeout=30.0) as c:
                for s in pending:
                    try:
                        st = c.get(f"{CFG.base}/v1/investigations/{s.inv_id}").json()
                        s.status = st
                        s.final_state = st.get("status", "")
                        ev = c.get(f"{CFG.base}/v1/investigations/{s.inv_id}/events",
                                   params={"since_seq": seen_seq[s.inv_id]}).json()
                    except Exception as exc:  # noqa: BLE001
                        s.error = f"{type(exc).__name__}: {exc}"
                        continue
                    if ev:
                        seen_seq[s.inv_id] = max(e["seq"] for e in ev)
                        s.kernel_events.extend(ev)
                        for e in ev:
                            TRACE.add(s.inv_id, "kernel", "event", e["event_type"],
                                      json.dumps(e.get("payload", {}))[:600],
                                      meta={"seq": e["seq"]})
            time.sleep(0.6)
        for s in live:
            if s.final_state not in TERMINAL_STATES:
                s.error = s.error or (
                    f"did not reach a terminal state within {CFG.poll_timeout_s}s "
                    f"(last={s.final_state or 'unknown'})")
                TRACE.add(s.inv_id, "flow", "error", "poll timeout", s.error)

    def _collect_reports(self) -> None:
        for s in self.sessions:
            if not s.created or s.final_state not in (LifecycleState.completed,
                                                      LifecycleState.reporting):
                continue
            try:
                with httpx.Client(timeout=30.0) as c:
                    r = c.get(f"{CFG.base}/v1/investigations/{s.inv_id}/report")
                r.raise_for_status()
                s.report = ReportResponse.model_validate(r.json())
                TRACE.add(s.inv_id, "flow", "report", "verification report fetched",
                          f"{len(s.report.report_markdown)} chars at {s.report.report_path}")
            except Exception as exc:  # noqa: BLE001
                s.error = f"{type(exc).__name__}: {exc}"
                TRACE.add(s.inv_id, "flow", "error", "report fetch failed", s.error)

    # ── projection for the dashboard ─────────────────────────────────────────

    def as_dict(self) -> dict:
        return {
            "state": self.state,
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed_s": round((self.finished_at or time.time()) - self.started_at, 1)
                         if self.started_at else 0.0,
            "sessions": [s.as_dict() for s in self.sessions],
            "primary_id": (self.primary().inv_id if self.primary() else ""),
            "sandbox": SANDBOX.as_dict(),
            "precheck": self.precheck,
            "plans": [p.as_dict() for p in PLANS.all()],
            "report_ready": bool(self.terminal_report),
        }


RUN = FlowRun()


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 8 — the terminal verification report
# ══════════════════════════════════════════════════════════════════════════════
# Printed in the terminal after the browser run finishes. Every line is a check with
# a PASS/FAIL and the evidence it was decided on. Nothing here is asserted from the
# script's intent — each check reads the kernel's own events, lifecycle states and
# generated report. Checks that cannot be decided say INCONCLUSIVE rather than
# guessing, because a demonstration that lies about its own coverage is worse than
# one that admits a gap.

_PASS, _FAIL, _INCONC = "PASS", "FAIL", "INCONCLUSIVE"


def _events_of(s: Session, event_type: str) -> list[dict]:
    return [e for e in s.kernel_events if e.get("event_type") == event_type]


def _claim_types(s: Session) -> set[str]:
    return {(e.get("payload") or {}).get("claim_type", "")
            for e in _events_of(s, kernel_events.ClaimAdmitted)} - {""}


def build_terminal_report(run: FlowRun) -> str:
    """Assemble the final report. Pure over `run` — safe to call twice."""
    L: list[str] = []
    checks: list[tuple[str, str, str]] = []   # verdict, name, evidence

    def check(cond: bool | None, name: str, evidence: str) -> None:
        verdict = _INCONC if cond is None else (_PASS if cond else _FAIL)
        checks.append((verdict, name, evidence))

    primary = run.primary()
    files = next((s for s in run.sessions if s.role == "files"), None)
    cancelled = next((s for s in run.sessions if s.role == "cancelled"), None)

    L.append("═" * 78)
    L.append(" WIZARD RUNTIME KERNEL — END-TO-END VERIFICATION REPORT")
    L.append(f" repository : {CFG.repo_path}")
    L.append(f" surface    : {CFG.base}")
    L.append(f" elapsed    : {round((run.finished_at or time.time()) - run.started_at, 1)}s"
             f"   driver state: {run.state}")
    L.append("═" * 78)

    # ── 1. sandbox ────────────────────────────────────────────────────────────
    sb = SANDBOX
    L.append("")
    L.append("1. SANDBOX (driven directly, before any investigation existed)")
    L.append(f"   runtime        : {sb.runtime_class} (mode={sb.mode})")
    L.append(f"   docker         : {sb.docker_available}")
    if sb.exec_result is not None:
        L.append(f"   exec           : exit={sb.exec_result.exit_code} "
                 f"stdout={sb.exec_result.stdout.strip()[:60]!r} "
                 f"{sb.exec_result.duration_ms}ms")
    if sb.bg_started is not None:
        L.append(f"   background     : handle={sb.bg_started.handle_id} "
                 f"output_bytes={len(sb.bg_polled.stdout_so_far) if sb.bg_polled else 0} "
                 f"listed={sb.listed} killed={sb.killed}")
    L.append(f"   tools driven   : {', '.join(sorted(sb.tool_results)) or '(none)'}")
    if sb.errors:
        L.append(f"   errors         : {'; '.join(sb.errors)}")

    check(sb.started and sb.exec_result is not None and sb.exec_result.exit_code == 0,
          "sandbox exec ran and returned exit 0",
          f"CommandResult.exit_code="
          f"{sb.exec_result.exit_code if sb.exec_result else 'n/a'}")
    check(bool(sb.bg_started and sb.bg_polled and sb.bg_polled.stdout_so_far and sb.killed),
          "sandbox background process started, produced output, was killed",
          f"handle={sb.bg_started.handle_id if sb.bg_started else 'n/a'}")    
    check(sb.bytes_read > 0, "sandbox read_file returned bytes",
          f"{sb.bytes_read} bytes")
    check(all(t.ok for t in sb.tool_results.values()) and len(sb.tool_results) >= 4,
          "ToolExecutor envelopes parsed back as ToolResult",
          f"{len(sb.tool_results)} tools, ok="
          f"{sorted(k for k, v in sb.tool_results.items() if v.ok)}")

    # ── 2. repository precheck ────────────────────────────────────────────────
    pc = run.precheck
    L.append("")
    L.append("2. REPOSITORY (world.repository.validate + world.scanner.scan)")
    for k in ("valid", "error", "files", "dirs", "key_files", "top_extensions",
              "size_bytes", "max_depth"):
        if k in pc:
            L.append(f"   {k:<15}: {pc[k]}")
    check(pc.get("valid") is True, "repository validated by the kernel",
          str(pc.get("error", "world.repository.validate raised nothing")))
    check((pc.get("files") or 0) > 0, "scanner produced a manifest",
          f"{pc.get('files')} files / {pc.get('dirs')} dirs, "
          f"key_files={pc.get('key_files')}")

    # ── 3. sessions and lifecycle ─────────────────────────────────────────────
    L.append("")
    L.append("3. SESSIONS (created over the kernel's own HTTP API)")
    for s in run.sessions:
        L.append(f"   {s.role:<10} {s.inv_id or '(not created)':<22} "
                 f"state={s.final_state or '?':<10} budget={s.request.options.budget:<3} "
                 f"browser={str(s.request.options.browser_enabled):<5} "
                 f"nodes={s.status.get('nodes_completed', '?')} "
                 f"claims={s.status.get('claims_count', '?')} "
                 f"events={len(s.kernel_events)}")
        if s.error:
            L.append(f"              error: {s.error}")

    check(len([s for s in run.sessions if s.created]) == 3,
          "three concurrent investigations created",
          f"{len([s for s in run.sessions if s.created])}/3 returned 201")
    check(bool(cancelled and cancelled.deleted
               and cancelled.final_state == LifecycleState.cancelled),
          "one session deleted mid-flight and stayed cancelled",
          f"state={cancelled.final_state if cancelled else 'n/a'}")
    check(bool(primary and primary.final_state == LifecycleState.completed),
          "primary session reached completed",
          f"state={primary.final_state if primary else 'n/a'}")
    check(bool(files and files.final_state == LifecycleState.completed),
          "non-browser session reached completed",
          f"state={files.final_state if files else 'n/a'}")
    check(bool(primary and files
               and primary.status.get("nodes_completed", 0)
                   > files.status.get("nodes_completed", 0)),
          "browser session ran strictly more nodes than the non-browser one",
          f"primary={primary.status.get('nodes_completed') if primary else '?'} vs "
          f"files={files.status.get('nodes_completed') if files else '?'}")

    L.extend(_report_agent_section(run, primary, files, check))
    L.extend(_report_browser_section(primary, check))
    L.extend(_report_belief_section(run, primary, files, check))

    # ── verdict ───────────────────────────────────────────────────────────────
    fails = [c for c in checks if c[0] == _FAIL]
    inconc = [c for c in checks if c[0] == _INCONC]
    L.append("")
    L.append("─" * 78)
    L.append(" CHECKS")
    L.append("─" * 78)
    for verdict, name, evidence in checks:
        L.append(f" [{verdict:<12}] {name}")
        L.append(f"                {evidence}")
    L.append("─" * 78)
    L.append(f" {len(checks)} checks — {len(checks) - len(fails) - len(inconc)} pass, "
             f"{len(fails)} fail, {len(inconc)} inconclusive")
    L.append(f" VERDICT: {'VERIFIED' if not fails and not inconc else ('FAILED' if fails else 'PARTIAL')}")
    L.append("═" * 78)

    for s in run.sessions:
        if s.report is not None:
            L.append("")
            L.append(f" kernel report for {s.role} ({s.inv_id}) — {s.report.report_path}")
            L.append("─" * 78)
            L.append(s.report.report_markdown.rstrip())
    return "\n".join(L)


def _report_agent_section(run: FlowRun, primary: Session | None, files: Session | None,
                          check) -> list[str]:
    """The three agent seams. The no-fallback rule is enforced here: every
    agent.decided event must carry source == "explorer". loop.py's node_plan branch is
    invariant-4 safety code and stays in the kernel, but if it ever fires the Explorer
    failed to answer or its request was rejected — and this run claims neither
    happens, so the check FAILs rather than tolerating it."""
    L = ["", "4. AGENTS (deterministic rule engines, no model, reached over real HTTP)"]
    live = [s for s in run.sessions if s.created]
    decided = [e for s in live for e in _events_of(s, kernel_events.AgentDecided)]
    by_source: dict[str, int] = {}
    for e in decided:
        src = (e.get("payload") or {}).get("source", "?")
        by_source[src] = by_source.get(src, 0) + 1
    consulted = [e for s in live for e in _events_of(s, kernel_events.AgentConsulted)]
    rejected = [e for s in live for e in _events_of(s, kernel_events.ToolRejected)]

    L.append(f"   planner        : {CFG.base}/plan/[initial|next|interpret]")
    L.append(f"   explorer       : {CFG.base}/agent/explorer")
    L.append(f"   verifier       : {CFG.base}/agent/verifier  "
             f"(consulted every {KERNEL_SURFACE['verifier_interval']} nodes)")
    L.append(f"   agent.decided  : {by_source}")
    L.append(f"   agent.consulted: {len(consulted)}")
    L.append(f"   tool.rejected  : {len(rejected)}"
             + (f"  ({', '.join(sorted({(e.get('payload') or {}).get('node_id', '?') for e in rejected}))})"
                if rejected else ""))
    for p in PLANS.all():
        d = p.as_dict()
        L.append(f"   plan[{d['inv_id'][:12]}]: phases={d['phases_emitted']} "
                 f"interpreted={d['interpreted_nodes']} "
                 f"mirror={d['mirror_checks']} checks/{d['mirror_rejections']} rejected")

    check(len(decided) > 0, "the Explorer was consulted and decided real tool requests",
          f"{len(decided)} agent.decided events")
    check(by_source.get("node_plan", 0) == 0,
          "no decision fell back to the node plan (no-fallback rule)",
          f"sources={by_source} — node_plan must be 0")
    check(len(consulted) > 0, "the Verifier was consulted by the loop",
          f"{len(consulted)} agent.consulted events")

    # The blocked-egress node is the one rejection this run intends. Every other
    # rejection would mean the Explorer's self-check disagreed with the kernel.
    unintended = [e for e in rejected
                  if (e.get("payload") or {}).get("node_id") != "d13_blocked_egress"]
    check(not unintended,
          "the only tool rejection is the deliberate off-host navigation",
          f"unintended rejections: "
          f"{[(e.get('payload') or {}).get('node_id') for e in unintended] or 'none'}")

    # Phase release is evidence-gated, so the non-browser session must never see D.
    files_plan = PLANS.get(files.inv_id) if files and files.inv_id else None
    check(bool(files_plan and "D" not in files_plan.emitted),
          "phase D was withheld from the non-browser session",
          f"emitted={sorted(files_plan.emitted) if files_plan else 'n/a'}")
    primary_plan = PLANS.get(primary.inv_id) if primary and primary.inv_id else None
    check(bool(primary_plan and {"A", "B", "C", "D"} <= primary_plan.emitted),
          "all four phases were released to the browser session",
          f"emitted={sorted(primary_plan.emitted) if primary_plan else 'n/a'}")
    check(bool(primary_plan and primary_plan.interpreted),
          "planner.interpret minted nodes from runtime-only values",
          f"interpreted={sorted(primary_plan.interpreted) if primary_plan else 'n/a'}")
    return L


def _report_browser_section(primary: Session | None, check) -> list[str]:
    """The browser plane, judged on the narration events the kernel emitted — not on
    whether the script asked for the actions."""
    L = ["", "5. BROWSER (real Chromium, fail-closed egress, two-plane model)"]
    if primary is None or not primary.created:
        L.append("   primary session was never created — browser plane not exercised")
        check(False, "browser plane exercised", "no primary session")
        return L

    nav = _events_of(primary, kernel_events.BrowserNavigated)
    acted = _events_of(primary, kernel_events.BrowserActed)
    extracted = _events_of(primary, kernel_events.BrowserExtracted)
    urls = [(e.get("payload") or {}).get("url", "") for e in nav]
    verbs = sorted({(e.get("payload") or {}).get("tool", "")
                    for e in acted} - {""})

    L.append(f"   allowed domains: {primary.request.options.allowed_domains} "
             f"(backend={primary.request.options.browser_backend})")
    L.append(f"   navigated      : {len(nav)}")
    for u in urls:
        L.append(f"                    {u}")
    L.append(f"   acted          : {len(acted)} {verbs}")
    L.append(f"   extracted      : {len(extracted)}")
    L.append(f"   screencast     : ws://{CFG.host}:{CFG.port}"
             f"/v1/investigations/{primary.inv_id}/screencast")

    claims = _claim_types(primary)
    browser_claims = {c for c in claims if c.startswith("WEB")}
    L.append(f"   web claims     : {sorted(browser_claims)}")

    check(len(nav) >= 3, "browser navigated to the fixture pages and the kernel's own API",
          f"{len(nav)} browser.navigated events")
    check(bool(acted), "click and type actions reached the page",
          f"{len(acted)} browser.acted events {verbs}")
    check(bool(extracted), "page content was extracted",
          f"{len(extracted)} browser.extracted events")
    check({"WEB_NAV", "WEB_SNAPSHOT", "WEB_CLICK", "WEB_EXTRACT", "WEB_BACK",
           "WEB_TYPE", "WEB_SELF"} <= claims,
          "all six browser verbs produced admitted claims",
          f"admitted WEB* = {sorted(browser_claims)}")
    # The browser_action / page_content extractors author the bare "WEB" type. If the
    # kernel stopped doing that this must fail loudly, not be quietly dropped.
    check("WEB" in claims,
          "belief.extractors read the browser payloads (bare WEB claim type)",
          f"{'WEB present' if 'WEB' in claims else 'no WEB claim — extractor path broken'}")
    check("WEB_EGRESS" not in claims,
          "the off-host navigation was refused (fail-closed egress held)",
          "d13_blocked_egress admitted no WEB_EGRESS claim"
          if "WEB_EGRESS" not in claims else
          "example.org navigation SUCCEEDED — the allowlist did not hold")
    check(any(f"/v1/investigations" in u for u in urls),
          "the agent's browser rendered the kernel's own API surface",
          f"urls={urls[-1:] or 'none'}")
    return L


def _report_belief_section(run: FlowRun, primary: Session | None,
                           files: Session | None, check) -> list[str]:
    """Evidence, trust and goals. The arithmetic is the kernel's own — expected_belief()
    calls trust.compute rather than restating the numbers."""
    L = ["", "6. BELIEF (subjective logic, kernel arithmetic)"]
    L.append(f"   U0             : {KERNEL_SURFACE['prior_uncertainty_u0']}")
    L.append(f"   source weights : {KERNEL_SURFACE['source_weights']}")
    for tier in KERNEL_SURFACE["source_tiers"]:
        L.append(f"   one support @ {tier:<14}: belief {expected_belief(tier)}   "
                 f"one contradict: {expected_belief(tier, 'contradict')}")

    live = [s for s in run.sessions if s.created]
    for s in live:
        types = _claim_types(s)
        goals = [(e.get("payload") or {}).get("goal_name", "?")
                 for e in _events_of(s, kernel_events.GoalSatisfied)]
        failed = _events_of(s, kernel_events.NodeFailed)
        L.append("")
        L.append(f"   {s.role} ({s.inv_id})")
        L.append(f"     claim types  : {sorted(types)}")
        L.append(f"     goals closed : {goals}")
        L.append(f"     nodes failed : {len(failed)} "
                 f"{sorted({(e.get('payload') or {}).get('node_id', '?') for e in failed})}")

    # Extracted types are the proof that observations were read by the kernel's own
    # extractor registry — this module never authors PACKAGE / RUNTIME / EXECUTION /
    # FILESYSTEM in any ClaimTemplate.
    authored_by_extractors = {"PACKAGE", "RUNTIME", "EXECUTION", "FILESYSTEM"}
    ptypes = _claim_types(primary) if primary else set()
    check(authored_by_extractors <= ptypes,
          "belief.extractors produced every claim type no ClaimTemplate authors",
          f"missing={sorted(authored_by_extractors - ptypes) or 'none'}")

    pgoals = {(e.get("payload") or {}).get("goal_name", "")
              for e in _events_of(primary, kernel_events.GoalSatisfied)} if primary else set()
    expected_goals = {g.name for g in GOALS_BASE} | {GOAL_WEB.name}
    check(expected_goals <= pgoals,
          "every goal of the browser session was satisfied by evidence",
          f"unsatisfied={sorted(expected_goals - pgoals) or 'none'}")

    fgoals = {(e.get("payload") or {}).get("goal_name", "")
              for e in _events_of(files, kernel_events.GoalSatisfied)} if files else set()
    check(GOAL_WEB.name not in fgoals,
          "the non-browser session closed no browser goal",
          f"files goals={sorted(fgoals)}")

    # Deliberate negative controls: their claims must exist and score 0.0, which is
    # why they sit outside every goal's required set.
    negatives = {"FS_ABSENT", "PORT_CLOSED"}
    check(negatives <= ptypes,
          "contradicting evidence from the negative-control nodes was admitted",
          f"present={sorted(negatives & ptypes)} "
          f"(contradict belief = {expected_belief('execution', 'contradict')})")

    exhausted = [e for s in live for e in _events_of(s, kernel_events.BudgetExhausted)]
    reports = [e for s in live for e in _events_of(s, kernel_events.ReportGenerated)]
    L.append("")
    L.append(f"   budget.exhausted: {len(exhausted)}   report.generated: {len(reports)}")
    check(len(reports) >= 2, "the kernel generated its own verification reports",
          f"{len(reports)} report.generated events")
    return L

__FLOW_APPEND_MARKER__ = True
