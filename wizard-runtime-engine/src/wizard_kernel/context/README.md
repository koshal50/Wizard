# Context Engine

The **Context Engine** is the read-only projection layer of the Wizard Runtime Kernel.
It sits between the kernel's authoritative state (the Knowledge Graph, Goals,
Observations, Budget, and the current node) and the three untrusted intelligences that
consult it — the **Explorer**, **Verifier**, and **Investigation Planner** agents.

Its one job: **turn kernel state into exactly the view each agent is allowed to see —
and nothing more.**

```
        authoritative kernel state                 untrusted agents
   ┌──────────────────────────────────┐         ┌───────────────────────┐
   │ KnowledgeGraph · GoalEngine       │         │ Explorer  (n8n)       │
   │ ObservationStore · BudgetManager  │ ──────▶ │ Verifier  (n8n)       │
   │ InvestigationNode · Graph         │ Context │ Planner   (TS/LLM)    │
   └──────────────────────────────────┘  Engine └───────────────────────┘
              (writes here)              (read-only)     (read-only)
```

---

## 1. Why it exists (the philosophy)

The kernel's **invariant 3** says: *the Planner and Agents never see or write trust
scores, raw graph internals, or disbelief values.* Before the Context Engine, every call
site hand-built its own dict and hoped it stripped the right fields. That is fragile: one
forgotten key leaks trust into an agent prompt and the whole "deterministic verifier owns
the truth" guarantee is gone.

The Context Engine makes trust-stripping **structural, not incidental**:

- It is the **single place** that decides what an agent sees.
- It **never mutates state** — it only reads. It cannot, even by accident, admit a claim
  or move a trust score.
- Every supply is **audited** — an event records *which* sections went to *which* agent,
  so the whole context flow is inspectable after the fact.

It also solves a second problem: **prompt stability**. LLM backends (we target
open-source models behind a vLLM OpenAI-compatible endpoint) reuse a KV cache only when
the prompt *prefix* is byte-stable. The engine orders sections so the stable parts come
first — cheap, repeatable inference without paying to re-encode the system prompt every
call.

---

## 2. The two outputs (the key concept)

`build_context(...)` returns a `ContextBuildResult` with **two views of the same state**:

| Output | Shape | Who consumes it | Status |
|--------|-------|-----------------|--------|
| **`packet`** | a flat, trust-stripped `dict` | the agents **today** (Mock + Http ports) | **live** |
| **`sections`** | ordered `list[ContextSection]` | a real LLM backend's prompt (KV-ordered, budget-trimmed, audited) | **infrastructure ready** |

This duality is deliberate — it is "safe from both sides":

- The **packet** is byte-for-byte the contract the agents already expect. Wiring in the
  Context Engine changed **nothing** for `MockExplorer` / `HttpExplorer`.
- The **sections** are the additive future: when a vLLM backend renders prompts, it
  consumes the ordered, trimmed, cache-friendly sections. Until then they still earn their
  keep by driving the token budget and the audit trail.

The explorer **packet** looks exactly like this:

```json
{
  "investigation_id": "inv_ab12cd",
  "intent": "understand the deployment architecture",
  "targets": ["architecture", "deployment"],
  "current_node": { "id": "node_9f3a1c", "type": "read",
                    "action": {"tool": "read_file", "params": {"path": "Dockerfile"}},
                    "goal_id": "goal_docker" },
  "active_goals": [ {"id": "goal_docker", "name": "Verify Docker Build", "state": "open"} ],
  "kg_summary": { "claims_count": 3, "high_trust_claims": [ ... ], "contradictions": [] },
  "remaining_budget": 27
}
```

Note what is **absent**: no trust floats, no belief/disbelief, no raw graph edges, no raw
observation payloads. That absence is the invariant, enforced in one place.

---

## 3. The pipeline

`build_context()` runs these stages (some architecture stages are folded together under
YAGNI — noted inline):

1. **Build packet** — always; cheap and deterministic; this is the agent contract.
2. **Cache check** — keyed `agent_type:node_id:state_version`. A hit returns instantly and
   is still audited (`from_cache=True`).
3. **Package into sections** *(Reader + Compressor folded in)* — field selection *is* the
   invariant-3 filter; last-N summary lines *are* the compression.
4. **Interceptor** — an input-side gate (proceed / rewrite / reject). Ships with **zero
   listeners**; it's a seam for future input policy, distinct from the existing
   `ToolRequestValidator` which gates agent *output*.
5. **Token budget + KV ordering** — order `stable → growing → volatile`; drop
   lowest-priority sections if over budget.
6. **Cache** the fitted sections.
7. **Audit** — emit a `context_supplied` event (section ids + token total, never content).

`on_state_mutation()` bumps the cache version, so once a claim is admitted or the budget
moves, the next projection is rebuilt fresh — a stale view is never served.

---

## 4. Section registry & KV classes

Sections carry `{id, priority, scope, content, token_cost}`. Higher priority survives
trimming; the KV class fixes prompt order for cache reuse.

**Explorer sections (live today):**

| id | priority | KV class |
|----|----------|----------|
| `system_instructions` | 100 | stable |
| `available_tools` | 90 | stable |
| `repository_summary` | 80 | stable |
| `verified_claims` | 75 | growing |
| `unverified_assumptions` | 70 | volatile |
| `recent_observations` | 60 | volatile |
| `recent_failures` | 50 | volatile |
| `budget_status` | 40 | volatile |

**Verifier sections (planned):** `claims_under_review` (90), `contradictions` (85),
`evidence_gaps` (80).
**Planner sections (planned):** `graph_topology` (90), `verifier_feedback` (85),
`newly_discovered` (80), `blocked_nodes` (75), `failed_nodes` (70).

`stable` (system/tools/repo) never changes within an investigation → longest reusable
prefix. `growing` (verified claims) only appends. `volatile` (assumptions, recent obs,
budget) changes every step → always last, so it never invalidates the cached prefix.

---

## 5. How the **Explorer** uses it — LIVE

The Explorer decides *how* to execute the current node. This path runs today and is
covered by tests. Diksha's agent lives on branch **`feature/wizard-agents`** as an
**n8n webhook**; the kernel reaches it through `HttpExplorer` when `agent_explorer_url` is
set in the investigation options, otherwise `MockExplorer` runs.

```mermaid
sequenceDiagram
    participant Loop as control/loop.py
    participant CE as ContextEngine
    participant Ex as Explorer (n8n / mock)
    participant V as ToolRequestValidator
    participant W as ToolExecutor

    Loop->>CE: build_context("explorer", inv, node, goals, kg, budget, obs_store)
    CE-->>Loop: ctx.packet (+ ctx.sections, audited)
    Loop->>Ex: explorer.request(ctx.packet)
    Ex-->>Loop: ExplorerResponse{ tool_request{tool, parameters, reason} }
    Loop->>V: validate(tool_request, budget.remaining)
    V-->>Loop: valid → sanitised params  (else fallback to node.action)
    Loop->>W: execute sanitised action
    W-->>Loop: immutable Observation → extractors → EvidenceEngine → KG
    Note over Loop,CE: next iteration: on_state_mutation() invalidates cache
```

**Step by step** (see `loop.py` `_run_loop` / `_resolve_tool_action`):

1. The loop selects the highest-priority ready node.
2. `ctx = context_engine.build_context("explorer", inv, node, goals, kg, budget, obs_store)`
   builds the packet, orders/trims sections, caches, and emits `context_supplied`.
3. `explorer.request(ctx.packet)`:
   - **`MockExplorer`** reads `packet["current_node"]["action"]` and faithfully echoes the
     Planner's planned action as a `ToolRequest` (so tests exercise the real extractor and
     claim pipeline, not a generic `list_tree`).
   - **`HttpExplorer`** POSTs the packet JSON to the n8n webhook and parses the reply as
     `ExplorerResponse`. (It defensively re-strips `trust` / `knowledge_graph_raw` before
     sending — belt-and-braces on top of the engine's guarantee.)
4. The returned `ToolRequest` is validated **deterministically** by `ToolRequestValidator`
   (sandbox policy, path-traversal guard, duplicate-fingerprint loop breaker). Agent input
   never reaches the OS unchecked.
5. Valid → the sanitised `{tool, params}` runs; invalid **or** agent error → the loop falls
   back to the node's own planned action, re-validated (invariant 4: an agent failure is
   never a crash).
6. The result becomes an **immutable Observation**; extractors + `EvidenceEngine` admit
   claims; the KG and trust move — **all kernel-side**, never by the agent.
7. On the next iteration `on_state_mutation()` invalidates the cache so the Explorer's next
   packet reflects the claims just learned.

**What the Explorer returns** (`contracts/agent.py`):

```python
ExplorerResponse(investigation_id="inv_ab12cd",
                 tool_request=ToolRequest(tool="read_file",
                                          parameters={"path": "Dockerfile"},
                                          reason="inspect base image + exposed ports"))
```

---

## 6. How the **Verifier** uses it — SEAM (how to wire)

The Verifier is consulted periodically (every `_VERIFIER_INTERVAL` completed nodes, = 5) to
review admitted claims. It is **advisory only** — it can never set trust, satisfy goals,
or mutate the graph; the Runtime independently decides whether to act on its opinion. It
too is an **n8n webhook** on `feature/wizard-agents`, reached via `HttpVerifier` when
`agent_verifier_url` is set, else `MockVerifier`.

**Today** `_consult_verifier` hand-builds a claims list and calls `verifier.assess(...)`.
Routing it through the Context Engine centralises the trust-stripping. The engine currently
raises `NotImplementedError("context ... for 'verifier' not built yet")` — an explicit seam,
not a silent empty context.

**To wire it (three edits):**

1. **Packager** — add `build_verifier_packet(...)` and `build_verifier_sections(...)`
   producing the planned sections: `claims_under_review` (the same trust-stripped
   `{claim_id, type, key, value}` list `_consult_verifier` builds today), `contradictions`
   (from `CONTRADICTS` graph edges), and `evidence_gaps` (open goals' missing claim types).
2. **Engine** — in `_build_packet` / `_build_sections`, add the `elif agent_type ==
   "verifier"` branch that calls the new packager methods (remove the `NotImplementedError`).
3. **Loop** — in `_consult_verifier`, replace the ad-hoc `claims_payload` with:
   ```python
   ctx = context_engine.build_context("verifier", inv, None, goals, kg, budget, obs_store)
   assessment = verifier.assess(ctx.packet["claims_under_review"])
   ```
   The port contract `assess(claims) -> VerifierAssessment` is **unchanged** — the engine
   just becomes the one place that builds `claims_under_review`.

**What the Verifier returns** (advisory; consumed by the Runtime, not obeyed):

```python
VerifierAssessment(investigation_id="inv_ab12cd",
                   assessment="needs_more_work",              # or "overall_sufficient"
                   weak_claims=["claim_7f2"],
                   recommended_additional_investigations=["confirm PACKAGE versions"])
```

If (and only if) the Runtime agrees there is a gap, it asks the Planner for more nodes —
which is the next section.

---

## 7. How the **Investigation Planner** uses it — SEAM (how to wire)

The Planner is Yash's service on branch **`yash-code`**
(`wizard-investigation-planner/`, TypeScript, provider-agnostic LLM behind a vLLM
OpenAI-compatible endpoint). The kernel reaches it through `HttpPlanner` when a planner URL
is configured, else the deterministic `MockPlanner`. It has three port methods:

| Port method | HTTP endpoint | Consumes context? | Returns |
|-------------|---------------|-------------------|---------|
| `initial(manifest, intent, targets)` | `POST /plan/initial` | no (uses the manifest) | `TechnologyPlan{technologies, seed_nodes}` |
| `next_nodes(context)` | `POST /plan/next` | **yes — this is the projection** | `list[InvestigationNode]` |
| `interpret(node, obs)` | `POST /plan/interpret` | no (node + one observation) | `list[InvestigationNode]` |

`next_nodes(context)` is the call the Context Engine should feed. **Today** the loop passes
ad-hoc dicts at two sites — the "need more work" branch and the verifier-gap branch — e.g.
`{investigation_id, reason, kg_summary, missing_evidence}`. The planner packet is
**explicitly not built yet** (the engine raises `NotImplementedError` for `"planner"`).

**To wire it:**

1. **Packager** — add `build_planner_packet(...)` / `build_planner_sections(...)` for the
   planned sections: `graph_topology`, `verifier_feedback`, `newly_discovered`,
   `blocked_nodes`, `failed_nodes`. Unlike the Explorer, the planner projection needs the
   **`InvestigationGraph`** handle (for topology / blocked / failed nodes) — so
   `build_context` gains a `graph=None` parameter that the planner branch requires.
2. **Engine** — add the `"planner"` branch in `_build_packet` / `_build_sections`.
3. **Loop** — replace both ad-hoc `planner.next_nodes({...})` dicts with:
   ```python
   ctx = context_engine.build_context("planner", inv, None, goals, kg, budget, obs_store, graph=graph)
   new_nodes = planner.next_nodes(ctx.packet)
   ```
   `HttpPlanner` POSTs that packet to `/plan/next`; Yash's service returns nodes that
   validate as `InvestigationNode` (snake_case: `action:{tool,params}`, `hypothesis:{kind}`,
   optional `on_success: ClaimTemplate`). The port contract is **unchanged**.

The Planner must keep emitting the kernel's Pydantic contracts exactly and must never
include trust/graph fields — the strict `PlannerValidator` on Yash's side already rejects
smuggled runtime fields, and the Context Engine guarantees none are sent *to* it in the
first place.

---

## 8. Cross-service map

| Agent | Branch | Transport | Kernel port | Selected by option |
|-------|--------|-----------|-------------|--------------------|
| Explorer | `feature/wizard-agents` | n8n webhook (HTTP) | `HttpExplorer` / `MockExplorer` | `agent_explorer_url` |
| Verifier | `feature/wizard-agents` | n8n webhook (HTTP) | `HttpVerifier` / `MockVerifier` | `agent_verifier_url` |
| Planner  | `yash-code` | HTTP service `/plan/*` | `HttpPlanner` / `MockPlanner` | planner URL |

When no URL is set, the kernel falls back to the deterministic Mock ports so the loop runs
end-to-end with **zero external services and zero cost** — the default for tests and CI.

---

## 9. Invariants the engine upholds

- **3 — agents never see trust/graph internals:** enforced in one place; the packet's key
  set is closed, and section renderers emit summaries (`VERIFIED: type:key = value`), never
  raw payloads or trust floats.
- **6 — investigations never share state:** one `ContextEngine` per investigation; the
  cache and audit bus are per-investigation.
- **3 (write side) — the engine is read-only:** it holds no authority to admit claims or
  move trust. It reads handles and returns views.
- **Auditability:** every supply emits `context_supplied` on the `EventBus`, so the CLI's
  live stream and any WebSocket consumer can see exactly what context each agent received.

---

## 10. Status

| Component | State |
|-----------|-------|
| Explorer packet + sections, KV order, budget, cache, audit, loop wiring | **live, tested** |
| Interceptor seam (zero listeners) | **live** |
| Verifier packager + sections | **seam — `NotImplementedError`, wire per §6** |
| Planner packager + sections | **seam — `NotImplementedError`, wire per §7** |

Files: `sections.py` · `packager.py` · `budget.py` · `cache.py` · `audit.py` ·
`interceptor.py` · `engine.py`. Tests: `../../../tests/test_context_engine.py` (20 tests).
Architecture source: `wizard-context-engine-final-architecture.md`.
