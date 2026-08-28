# Wizard Investigation Kernel — Build Design (Shivam)

**Owner:** Shivam (Runtime Engine)  
**Status:** Canonical design for teammates to build against  
**Platform:** Windows 10/11 (primary development machine)  
**Source of truth for product rules:** `docs/main/*`  
**This document:** how Shivam builds the Runtime so Koshal, Yash, and Diksha never block or break each other

---

## 1. What this module is

Wizard’s Runtime is **not** an AI agent and **not** a language-specific analyzer.

It is an **Investigation Kernel**:

> Intelligence (Planner / Agents) proposes structured experiments.  
> The Kernel runs them safely, logs immutable reality, admits claims only with evidence, scores trust, tracks goals, and projects a verification report.

Slogan:

```text
Keep reality. Gate belief. Explain everything.
```

Everyone else plugs into **ports**. They never write claims, trust, or goals directly.

```text
Koshal (CLI)  ──InvestigationRequest──►  KERNEL  ◄── TechnologyPlan / Nodes ── Yash (Planner)
                                            │
                                            │ ToolRequest / Assessment
                                            ▼
                                         Diksha (Agents / n8n)
```

---

## 2. Lessons from real open-source systems (100+ stars)

Only proven, high-star systems informed this design. Ponytail is listed for philosophy only (skill/prompt product, not a kernel).

| Project | Stars (approx) | Language | What we steal | What we do **not** copy |
|---|---|---|---|---|
| **SWE-agent** ([SWE-agent/SWE-agent](https://github.com/SWE-agent/SWE-agent)) | ~20k | Python | **Action → Environment → Observation** loop; ACI idea: thin, stable tool surface; trajectory logging | Issue-fixing agent brain; becoming an LLM chat loop |
| **SWE-ReX** ([SWE-agent/SWE-ReX](https://github.com/SWE-agent/SWE-ReX)) | ~550 | Python | **Abstract Runtime interface** (local / Docker / remote); shell sessions; exit code + stdout as first-class; agent logic ≠ infrastructure | Full cloud backends day one |
| **OpenHands** ([OpenHands/OpenHands](https://github.com/OpenHands/OpenHands) + agent-sdk) | ~80k | Python/TS | **Strict layer boundaries**; apps talk via **API**; **immutable typed models** + **one mutable investigation state**; Docker sandbox on Windows via Docker Desktop | Embedding Planner/Agents inside Kernel; mandatory mega-framework |
| **AIOS** ([agiresearch/AIOS](https://github.com/agiresearch/AIOS)) | ~6k | Python | Kernel manages **scheduling, memory, tools** — not “thinking” | OS-in-OS complexity; putting LLM inside the kernel |
| **LangGraph** ([langchain-ai/langgraph](https://github.com/langchain-ai/langgraph)) | ~37k | Python | Graph state machine **inspiration** (nodes, edges, checkpoints) | Hard dependency on LangChain stack for core truth path |
| **Ponytail** ([DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail)) | very high (skill plugin) | mostly rules/skills | **Minimalism**: do not overbuild; smallest correct system | It is not a runtime/kernel — do not treat it as architecture |

### Proven patterns we adopt

1. **Observation is the unit of reality** (SWE-agent / OpenHands event stream).  
2. **Sandbox is a pluggable backend** (SWE-ReX Runtime interface).  
3. **Schemas are contracts** (OpenHands Pydantic immutability).  
4. **Kernel is dumb, strict, and central** (AIOS).  
5. **Build the smallest loop that works** (Ponytail ethos + mini-SWE-agent lesson: simple > sprawling).

### What makes Wizard different (our contribution)

Those systems run agents. **We run an evidence court.**

```text
Their loop:   LLM decides → tool → observe → LLM decides
Our loop:     Planner/Agent proposes node with HYPOTHESIS
              → Kernel executes → Observation
              → Hypothesis match admits Claim + Evidence
              → Trust / Goals / Priority
              → unexpected → escalate (not invent)
```

Dual memory by construction:

| Graph | Question |
|---|---|
| Investigation Graph | How did we act? |
| Knowledge Graph | What do we believe? |

---

## 3. Tech stack decision (Windows-first)

### Decision: **Python 3.11+** for the Kernel

| Option | Verdict for Kernel | Why |
|---|---|---|
| **Python 3.11+** | **Chosen** | Every serious agent kernel above is Python-first; best sandbox/process/Docker SDK; Pydantic schemas; pytest; works natively on Windows |
| TypeScript / Node | Rejected for Kernel | Fine for UI/CLI later; weaker untrusted-process + research sandbox ecosystem; Koshal/Yash can still use JS if they want **clients**, not the kernel |
| Pure Go/Rust | Rejected for FYP | Strong isolation later; too much implementation cost for 4-person project |

### Recommended stack (concrete)

| Layer | Choice | Notes |
|---|---|---|
| Language | Python 3.11+ | Install from python.org on Windows |
| Package/env | `uv` or `venv` + `pip` | `uv` is fast; either is fine |
| API server | **FastAPI** + **Uvicorn** | REST for CLI + Planner + Agents |
| Schemas | **Pydantic v2** | Single source of truth for all contracts |
| HTTP client (out) | `httpx` | Call n8n / Planner HTTP |
| Async | FastAPI async where I/O; sync OK for sandbox ops | Don’t over-async early |
| Storage (v1) | **Filesystem JSON** under `.wizard/investigations/{id}/` | Simple, auditable, no DB required |
| Storage (v2 optional) | SQLite | Only if JSON becomes painful |
| Sandbox (prod path) | **Docker Desktop** on Windows | Same approach OpenHands documents for Windows |
| Sandbox (dev path) | **LocalProcessRuntime** | Restricted cwd; **not** for untrusted repos in demos |
| Docker control | `docker` CLI via subprocess **or** `docker` Python SDK | Prefer CLI first (fewer deps, easier debug) |
| Tests | `pytest` | Contract tests are mandatory |
| Lint | `ruff` | Optional but recommended |
| Report | Jinja2 or plain Python f-strings → `verification_report.md` | No LLM inventing report text |

### Windows requirements (no Linux install)

You do **not** need WSL or a Linux machine.

Required on your Windows PC:

1. **Python 3.11+**
2. **Git**
3. **Docker Desktop for Windows** (for real sandbox demos)
   - WSL2 backend is installed by Docker Desktop itself — you are not “installing Linux as your OS”
4. Optional: VS Code + Python extension

If Docker Desktop is unavailable temporarily:

- Use `LocalProcessRuntime` only for unit tests and internal tooling  
- Mark investigations with `sandbox_mode: local_dev` and **do not claim** full isolation in the report

### Why not Node for the Kernel

Koshal can implement CLI in Python (Typer) *or* Node calling our REST API.  
Diksha stays on n8n.  
Yash can implement Planner as Python module or HTTP service.  

**The Kernel must be one language with strong process control.** That is Python.

---

## 4. Five-layer architecture (one system, not 14 products)

```text
PORTS:  CLI API  |  Planner Port  |  Agent Port
                    │
L1 SESSION ──────── Investigation Manager + Kernel + Events
L2 WORLD ────────── Repository + Fast Scan + Sandbox + Tools
L3 REALITY ──────── Observation Store (append-only)
L4 BELIEF ───────── Extract → Evidence → Knowledge Graph → Trust
L5 CONTROL ──────── Investigation Graph + Priority + Goals + Report
```

Map of doc “14 subsystems” → layers:

| Layer | Subsystems |
|---|---|
| L1 | Runtime Kernel, Investigation Manager, Event Bus |
| L2 | Repository Manager, Fast Scanner, Sandbox Manager, Tool Runtime |
| L3 | Observation Engine |
| L4 | Extractor Framework, Evidence Engine, Knowledge Graph, Trust Engine |
| L5 | Investigation Graph, Goal Engine, Priority Engine, Report Generator |

Build **layers**, not a microservice per name.

---

## 5. Core loop (the only algorithm that matters)

```text
start(request)
  create Investigation (budget, empty graphs)
  manifest = fast_scan(repo)
  plan = planner.initial(manifest, intent)     # mockable
  seed investigation_graph + goals from plan

while budget > 0 and not converged:
  node = priority.next_ready(investigation_graph, goals, trust)
  if node is None:
      if planner_can_extend: add nodes from planner.next(...)
      else: break

  result = tools.execute(node.action, sandbox)
  obs = observations.append(node, result)      # immutable

  match = hypothesis.evaluate(node.hypothesis, obs)
  if match == EXPECTED_SUCCESS:
      admit claim from node.on_success + evidence(obs)
  elif match == EXPECTED_FAILURE:
      admit claim from node.on_failure + evidence(obs)
  else:
      escalation = planner.interpret(node, obs)  # or agent
      admit only if escalation returns structured claims/nodes
      add any new nodes

  trust.recompute(affected_claims)
  goals.evaluate_checkpoints()
  budget -= 1

report = report_generator.project(investigation)
return report
```

Invariants (never violate):

1. Observations are immutable.  
2. Claims enter only through Evidence.  
3. Planner/Agents never write graphs or trust.  
4. Tool failures become Observations, not Kernel crashes.  
5. Kernel has **no** technology-specific meaning (`package.json` ≠ Node unless a node template says so).  
6. Investigations never share state.  
7. Budget always terminates the loop.

---

## 6. Repository layout (code you will create)

Proposed package under `wizard-runtime-engine/`:

```text
wizard-runtime-engine/
  pyproject.toml
  README.md
  src/wizard_kernel/
    __init__.py
    main.py                 # uvicorn entry
    api/
      app.py                # FastAPI app
      routes_investigations.py
      routes_health.py
      deps.py
    contracts/              # Pydantic models — TEAM CONTRACT SURFACE
      request.py
      manifest.py
      plan.py
      node.py
      observation.py
      claim.py
      evidence.py
      tool.py
      agent.py
      report.py
      status.py
    session/
      manager.py
      investigation.py
      budget.py
      events.py
    world/
      repository.py
      scanner.py
      sandbox/
        base.py             # Runtime protocol (SWE-ReX style)
        local.py
        docker.py
      tools.py
    reality/
      observations.py
    belief/
      extractors.py
      evidence.py
      knowledge_graph.py
      trust.py
    control/
      investigation_graph.py
      priority.py
      goals.py
      hypothesis.py
      loop.py               # THE main loop
      report.py
    ports/
      planner.py            # protocol + mock + http
      agents.py             # protocol + mock + http (n8n)
    storage/
      fs_store.py
  tests/
    test_contracts.py
    test_observations_immutable.py
    test_hypothesis.py
    test_trust.py
    test_loop_with_mocks.py
    test_api.py
  examples/
    mock_e2e.py
```

Teammates should only need:

- `contracts/*` (schemas)  
- `api` OpenAPI at `/docs`  
- this design doc  

---

## 7. Frozen contracts (what others build on)

These are **owned by Shivam**, agreed once, versioned as `contracts_version: "1.0"`.

### 7.1 CLI → Kernel: start investigation

`POST /v1/investigations`

```json
{
  "contracts_version": "1.0",
  "repository_path": "C:/path/to/repo",
  "intent": "verify",
  "targets": ["runtime", "dependencies"],
  "options": {
    "budget": 40,
    "sandbox_mode": "docker",
    "planner_url": null,
    "agent_explorer_url": null,
    "agent_verifier_url": null
  }
}
```

Response:

```json
{
  "investigation_id": "inv_01H...",
  "status": "created"
}
```

### 7.2 CLI → Kernel: poll

`GET /v1/investigations/{id}`

```json
{
  "investigation_id": "inv_01H...",
  "status": "running",
  "lifecycle": "investigation_loop",
  "budget_remaining": 27,
  "nodes_completed": 13,
  "claims_count": 8,
  "active_goals": [
    {"id": "goal_runtime", "state": "open", "progress": 0.6}
  ],
  "last_event": "executed node_014 npm install"
}
```

Lifecycle values: `created | scanning | planning | investigation_loop | reporting | completed | failed | cancelled`

### 7.3 CLI → Kernel: report

`GET /v1/investigations/{id}/report`

Returns markdown + structured JSON sidecar optional:

```json
{
  "investigation_id": "inv_01H...",
  "report_markdown": "# Verification Report\n...",
  "report_path": ".wizard/investigations/inv_01H.../verification_report.md"
}
```

### 7.4 Kernel → Planner (Yash)

Kernel **calls** Planner (in-process interface first, HTTP later).

**Initial plan request:**

```json
{
  "investigation_id": "inv_...",
  "intent": "verify",
  "targets": ["runtime"],
  "manifest": { "...RepositoryManifest..." }
}
```

**Initial plan response (Technology Plan + seed nodes):**

```json
{
  "technologies": [
    {
      "name": "Node.js",
      "confidence": "high",
      "signals": ["package.json"],
      "initial_goals": ["Verify Runtime", "Verify Dependencies"],
      "priority_files": ["package.json"]
    }
  ],
  "seed_nodes": [ { "...InvestigationNode..." } ]
}
```

**Next nodes / escalation:**

```json
{
  "investigation_id": "inv_...",
  "reason": "unexpected_outcome" | "need_more_work",
  "knowledge_summary": {},
  "recent_nodes": [],
  "missing_evidence": [],
  "unexpected": { "node_id": "n14", "observation_id": "o22", "payload_summary": "..." }
}
```

Response:

```json
{
  "new_nodes": [ { "...InvestigationNode..." } ],
  "notes": "optional free text ignored for truth"
}
```

**Yash never receives whole repo.** Only manifest + progressive file contents Kernel already observed.

### 7.5 InvestigationNode (shared with Yash)

```json
{
  "id": "node_003",
  "type": "execute",
  "action": {
    "tool": "execute_command",
    "params": { "command": "npm install", "cwd": "." }
  },
  "hypothesis": {
    "kind": "exit_code_in",
    "success_values": [0],
    "failure_values": [1, 2]
  },
  "on_success": {
    "claim_type": "DEPENDENCIES",
    "key": "installable",
    "value": true
  },
  "on_failure": {
    "claim_type": "DEPENDENCIES",
    "key": "installable",
    "value": false
  },
  "escalate_when": "exit_code_not_in_success_or_failure",
  "depends_on": ["node_001"],
  "parent_id": "node_000",
  "goal_id": "goal_dependencies"
}
```

Hypothesis kinds Kernel implements in v1 (extensible later):

| kind | meaning |
|---|---|
| `exit_code_in` | match process exit code |
| `stdout_contains` | substring / regex |
| `file_exists` | path exists after action |
| `json_path_equals` | parsed JSON path equals value |
| `http_status` | port/url check status |
| `always_success` | discovery/read always admits success template if tool ok |
| `manual_escalate` | always escalate (rare) |

### 7.6 Kernel → Agents (Diksha / n8n)

**Explorer** `POST {agent_explorer_url}`

Request = investigation context summary (goals, missing evidence, failed actions, available tools, budget).  
Response:

```json
{
  "investigation_id": "inv_...",
  "tool_request": {
    "tool": "execute_command",
    "parameters": { "command": "npm start", "cwd": "." },
    "reason": "need execution evidence for runtime"
  }
}
```

Kernel validates tool name/params, executes via Tool Runtime, returns observation summary to agent if multi-turn, **or** converts tool request into an InvestigationNode with hypothesis defaults.

**Verifier** `POST {agent_verifier_url}`

Request = claims + evidence + trust.  
Response:

```json
{
  "investigation_id": "inv_...",
  "assessment": "overall_sufficient" | "needs_more_work",
  "weak_claims": ["claim_..."],
  "recommended_additional_investigations": ["..."]
}
```

Kernel may open new goals/nodes from recommendations **only after structured validation**.  
Verifier cannot set trust.

### 7.7 Tools catalog (v1)

| tool | params | produces observation type |
|---|---|---|
| `list_tree` | `max_depth` | `filesystem` |
| `read_file` | `path`, `max_bytes` | `file_content` |
| `search_files` | `pattern`, `glob` | `search_hits` |
| `execute_command` | `command`, `cwd`, `timeout_sec` | `command_result` |
| `check_port` | `port`, `host` | `port_check` |
| `path_exists` | `path` | `path_check` |

All tools:

- run only inside active sandbox workspace  
- return structured `{ ok, data, error, meta }`  
- never mutate graphs  

---

## 8. Sandbox design (Windows-safe)

### Protocol (SWE-ReX inspired)

```python
class SandboxRuntime(Protocol):
    def start(self, workspace_host_path: str) -> None: ...
    def exec(self, command: str, cwd: str, timeout_sec: int) -> CommandResult: ...
    def read_file(self, path: str, max_bytes: int) -> bytes: ...
    def write_file(self, path: str, data: bytes) -> None: ...  # only if ever needed
    def stop(self) -> None: ...
```

### Docker mode (default for real investigations)

- Image: start with `python:3.12-slim` or multi-tool image later  
- Mount repo read-write into `/workspace`  
- Network: off by default; optional allowlist later  
- CPU/memory limits via `docker run --memory --cpus`  
- Kill on timeout  
- Destroy container after investigation  

Windows: Docker Desktop must be running. Document this in Kernel README.

### Local process mode (dev/tests only)

- `subprocess` with `cwd` locked under investigation workdir  
- env scrubbed  
- timeout via `subprocess.run(..., timeout=)`  
- **Never** present as secure isolation  

### Failures

Non-zero exit → Observation  
Timeout → Observation  
Sandbox unavailable → investigation `failed` with partial report if any data exists  

---

## 9. Belief & trust (v1 simple, correct)

### Claim admission

```text
Observation → (optional extractor) → candidate Claim
           → Evidence(support|contradict, source_cluster)
           → Knowledge Graph insert/update
           → Trust recompute
```

### Trust v1 (buildable)

```text
weight(execution) > weight(config_parse) > weight(documentation)

belief      = support / (support + contradict + u0)
disbelief   = contradict / (support + contradict + u0)
uncertainty = 1 - belief - disbelief
```

Rules:

- same observation id cannot double-count  
- contradictions never delete claims  
- dependents marked `stale` if foundational claim collapses  
- docs-only cannot fully satisfy verify goals (threshold requires execution evidence when goal type is verify)

Upgrade path later: Dempster–Shafer-style fusion. **Not required for v1.**

---

## 10. Priority & goals (v1)

### Priority

Ready nodes = dependencies satisfied and state `waiting`.

Score:

```text
score = goal_urgency + uncertainty_gap - cost_penalty - retry_penalty
```

Pick highest. No LLM.

### Goals / checkpoints

A checkpoint is satisfied when required claims exist with `belief >= threshold` and no critical contradiction open.

Convergence when:

- all active checkpoints satisfied, **or**  
- budget exhausted, **or**  
- no ready nodes and planner returns no new nodes  

---

## 11. Storage layout on disk

```text
{repo_or_global}/.wizard/investigations/{investigation_id}/
  meta.json
  manifest.json
  investigation_graph.json
  knowledge_graph.json
  observations/
    o_0001.json
    o_0002.json
  events.jsonl
  verification_report.md
```

JSON is enough for FYP demos and full audit.

---

## 12. Mock-first integration (so others never block you)

Implement three adapters:

| Port | Mock behavior |
|---|---|
| Planner | Returns fixed Technology Plan + seed nodes for a tiny sample repo |
| Explorer | Returns one scripted tool request |
| Verifier | Returns `overall_sufficient` after N claims |

**Kernel must pass full e2e with mocks only.**  
Then swap URLs to Yash/Diksha services.

This is how OpenHands-style boundaries prevent team deadlock.

---

## 13. Build phases (order that cannot fail logically)

### Phase 0 — Contracts freeze (team meeting)
- Publish OpenAPI + `contracts/` models  
- Koshal / Yash / Diksha sign off  

### Phase 1 — Session + API skeleton
- FastAPI health + create/status  
- FS storage  
- Investigation Manager  

### Phase 2 — World + Reality
- Repository load + Fast Scanner  
- Local + Docker sandbox  
- Tools + Observation store  

### Phase 3 — Control spine
- Investigation Graph  
- Hypothesis evaluator  
- Priority + budget loop  
- Mock planner  

### Phase 4 — Belief
- Claim schemas + evidence  
- Knowledge Graph  
- Trust v1  
- Checkpoints  

### Phase 5 — Report
- Project markdown only from graphs/observations  

### Phase 6 — Live ports
- HTTP Planner (Yash)  
- HTTP Agents (Diksha n8n)  
- CLI integration (Koshal)  

Do **not** start with n8n or fancy trust math.

---

## 14. Test plan (architecture-protecting tests)

Must-pass tests:

1. Observation cannot be mutated after write  
2. Claim without evidence rejected  
3. Agent payload cannot set trust  
4. Expected exit code admits success claim without planner  
5. Unexpected outcome calls planner port  
6. Docker sandbox cannot read host path outside mount (smoke)  
7. Budget stop yields partial report  
8. Report claim IDs resolve to observation IDs  
9. Two investigations isolated  
10. OpenAPI schema matches `contracts_version`  

Run with: `pytest -q`

---

## 15. What each teammate needs from you (checklist)

### Provide to Koshal
- [ ] Base URL + OpenAPI (`/docs`)  
- [ ] InvestigationRequest schema  
- [ ] status enum + progress fields  
- [ ] report endpoint  
- [ ] stable error format `{ "error": { "code", "message" } }`  

### Provide to Yash
- [ ] Manifest schema (coordinate ownership: Yash designs content, Kernel stores/validates)  
- [ ] TechnologyPlan + InvestigationNode schemas  
- [ ] Planner request/response schemas  
- [ ] Escalation payload  
- [ ] Mock planner example for local testing  

### Provide to Diksha
- [ ] Explorer request/response schemas  
- [ ] Verifier request/response schemas  
- [ ] Tool catalog + parameter JSON Schema  
- [ ] Rejection rules for invalid tool requests  
- [ ] Example n8n-compatible HTTP payloads  

### You need from them
- Koshal: intent mapping only uses your API  
- Yash: always valid JSON nodes; no free-form “truth”  
- Diksha: structured tool_request/assessment only  

---

## 16. Explicit non-goals (prevents scope explosion)

The Kernel will **not**:

- hardcode Node/Python/Docker semantics as product knowledge  
- embed n8n  
- call LLM for report prose (optional later for summaries only, still claim-grounded)  
- share state across investigations  
- require Linux as host OS  
- implement microservices per subsystem  
- depend on LangGraph/LangChain for the truth path  

---

## 17. Minimal dependencies (`pyproject.toml` sketch)

```toml
[project]
name = "wizard-kernel"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "pydantic>=2.8",
  "httpx>=0.27",
  "python-multipart>=0.0.9",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "ruff>=0.6"]
```

No heavy agent frameworks required.

---

## 18. How to run on Windows (target UX)

```powershell
cd wizard-runtime-engine
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# start API
uvicorn wizard_kernel.main:app --reload --port 8080

# open contracts
start http://127.0.0.1:8080/docs
```

Docker Desktop running for `sandbox_mode=docker`.

Koshal:

```text
POST http://127.0.0.1:8080/v1/investigations
```

---

## 19. Success criteria for Shivam’s module

You are done when:

1. Kernel runs end-to-end with **mocks only**  
2. CLI can start/poll/report against live Kernel  
3. Yash can plug Planner without Kernel code changes (URL/config)  
4. Diksha can plug n8n Explorer/Verifier without Kernel code changes  
5. Report is fully traceable Observation → Node → Claim  
6. No technology-hardcoded branches in Kernel core  
7. Works on **Windows + Docker Desktop**  

---

## 20. One-page mental model for the team

```text
┌─────────────────────────────────────────────────────────┐
│                 WIZARD INVESTIGATION KERNEL              │
│                      (Shivam / Python)                   │
│                                                         │
│   propose → execute → observe → match → admit → score   │
│                                                         │
│   Investigation Graph = how we acted                    │
│   Knowledge Graph     = what we believe                 │
│   Observations        = immutable reality               │
│   Report              = projection of state             │
└─────────────────────────────────────────────────────────┘
         ▲                ▲                 ▲
         │                │                 │
      Koshal           Yash              Diksha
       CLI            Planner            Agents
```

---

## 21. Next action for Shivam

1. Team 30-minute contract freeze on Section 7 schemas  
2. Scaffold `wizard-runtime-engine` package as above  
3. Implement Phase 1–3 with mock planner  
4. Publish OpenAPI link to Koshal/Yash/Diksha  
5. Only then integrate real Planner/Agents  

---

**End of design.**  
If anything in this document conflicts with `docs/main`, **`docs/main` product rules win**; this document wins on implementation choices (stack, packaging, Windows, ports, build order).
