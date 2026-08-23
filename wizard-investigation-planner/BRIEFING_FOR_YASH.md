# Briefing — Investigation Planner (for Yash)

> Status as of 2026-08-20. Branch `yash-code`. This project was moved from the
> repo root into `wizard-investigation-planner/` (history preserved; all 56 tests
> still pass; no rewiring was needed). This file explains what the Investigation
> Planner *is*, what has been built, and what to do next.

---

## Part 1 — What the Investigation Planner actually is

The Planner **replaced the old hardcoded "Knowledge Module" system**. Instead of a
developer writing a Node.js module, a Docker module, a Python module, and so on,
the Planner asks an LLM:

> "Given what we know about this repository so far, what should we investigate
> next, what do we expect to find, and what claim would that produce?"

That is what lets Wizard understand technologies nobody wrote a module for.

Three properties define it:

1. **It plans; it never acts.** It returns only *proposals*: an initial
   **Technology Plan**, and **Investigation Nodes** each carrying a `hypothesis`
   + `success_claim` + `failure_claim`. The **Runtime** executes them, owns both
   graphs, computes trust, and decides truth. The Planner **cannot** read files,
   run commands, write claims, set trust, create observations, or mark a goal
   complete.

2. **Progressive 3-tier context** — the Planner never receives the whole repo:
   - **Tier 1:** the Repository Manifest (metadata only — names, sizes, key files).
   - **Tier 2:** targeted file reads (only files that matter for the current step).
   - **Tier 3:** execution results (command output as observations).

3. **It minimizes LLM calls.** The Planner creates nodes; the Runtime evaluates
   most results *deterministically* by checking the node's hypothesis (exit 0 →
   success claim, non-zero → failure claim — no LLM). The Planner is only
   re-consulted on an **UNEXPECTED** result.

**The core principle it preserves:** *The Runtime owns truth. The Planner only
informs the investigation.*

---

## Part 2 — What has actually been built

### The good news — the planning brain is solid ✅

These parts faithfully implement the design above and are genuinely well done:

- `src/planner/*` — proposals-only facade (`InvestigationPlanner.ts`), split into
  technology / ongoing / escalation planners, plus a **strict validation gate**
  (`PlannerValidator.ts` + `schemas.ts`) that rejects any proposal trying to
  smuggle a runtime-owned field (`status`, `createdAt`, `observationId`, `trust`),
  confines read paths to the repo, and safety-checks execute commands.
- `src/llm/*` — provider-agnostic LLM layer. Defaults to an **offline
  `heuristic` provider** (zero API key, zero network, zero cost). The Claude line
  in `.env.example` is a **commented-out example only** — nothing requires a paid
  model. *The "we can't afford Claude" concern is already handled.*
- `src/manifest/*`, `src/scanner/*` — the Tier-1 manifest + fast scan.
- Real tests (56 passing), strict tsconfig, zero runtime deps.

### The problem — the wrong container was built around it ⚠️

The branch contains a **complete standalone re-implementation of the entire
engine** in TypeScript:

```
src/runtime/  src/graphs/  src/claims/  src/evidence/  src/trust/
src/observations/  src/report/
```

**Shivam's Python `wizard-runtime-engine/` already owns every one of those.** It
is the real engine. So the repo currently carries **two full engines that cannot
talk to each other.** This also contradicts the Planner's own contract — the doc's
"What the Planner Cannot Do" list says the Planner must not own graphs, trust, or
claims, yet this TypeScript version does.

The output contract drifted too. The TS plan/node JSON (`initialGoals`,
`priorityFiles`, camelCase, discriminated `action.type`, free-text hypothesis)
does **not** match the Python engine's Pydantic contracts.

---

## Part 3 — What to do next

**The integration seam already exists and is waiting for you.** In
`wizard-runtime-engine/src/wizard_kernel/ports/planner.py`:

```python
class HttpPlanner:
    """Calls Yash's planner service via HTTP. Phase 6."""
    # POSTs to /plan/initial, /plan/next, /plan/interpret
```

`get_planner(planner_url)` uses `HttpPlanner` when a URL is configured, otherwise
falls back to `MockPlanner`. **Your job is to build the service behind those three
endpoints — not another engine.**

Concrete steps (following the 7 principles):

1. **Reuse, don't rewrite (#2).** Keep `src/planner`, `src/llm`, `src/manifest`,
   `src/scanner` as the *brains*. **Delete** `src/runtime`, `src/graphs`,
   `src/claims`, `src/evidence`, `src/trust`, `src/observations`, `src/report` —
   Shivam's kernel owns those.

2. **The seam already exists → use it (#2, #5).** Wrap the planner in a small HTTP
   service exposing:
   - `POST /plan/initial`   → returns a `TechnologyPlan`
   - `POST /plan/next`      → returns `{ "new_nodes": [ ... ] }`
   - `POST /plan/interpret` → returns `{ "new_nodes": [ ... ] }`

3. **Match Shivam's contracts exactly (#7 — the minimum that works).** Emit what
   `HttpPlanner` deserializes, in **snake_case**, per
   `wizard-runtime-engine/src/wizard_kernel/contracts/{plan,node,manifest}.py`:
   - `TechnologyPlan { technologies: [...], seed_nodes: [...] }`
   - `TechnologyEntry { name, confidence, signals, initial_goals, priority_files }`
   - `GoalDefinition { name, required_claim_types, belief_threshold,
     requires_execution_evidence }` — the kernel reads these fields directly and
     **never** infers meaning from the goal `name`.
   - Node shape: `{ id, type, action: { tool, params }, hypothesis: { kind, ... },
     on_success: ClaimTemplate{ claim_type, key, value }, on_failure?, goal_id }`.

   **→ Agree this schema with Shivam before building — it's the one thing that
   must match on both sides.**

4. **Provider = free / open-source.** Keep `heuristic` as the default. For a real
   model, run **vLLM** (it serves an OpenAI-compatible `/v1/chat/completions` API)
   and use the existing `OpenAILLMProvider` pointed at it — **no new provider
   class, no Claude.** One fix: `src/llm/providerFactory.ts` doesn't yet pass
   `LLM_BASE_URL` into the provider (it's advertised in `.env.example` but ignored)
   — ~2 lines to wire it through.

5. **Small cleanup (#1).** Delete the stray `tests/__init__.py` (a Python file
   sitting in the TypeScript `tests/` dir).

---

## One-line summary

**Your planner brain is good. Throw away the engine you cloned, and expose the
brain as the `/plan/*` HTTP service Shivam's kernel is already coded to call —
matching his Pydantic contracts, and using vLLM (not Claude) for real runs.**

---

## The 7 principles (apply while doing the above)

1. Does this need to exist? → no: skip it (YAGNI)
2. Already in this codebase? → reuse it, don't rewrite
3. Stdlib does it? → use it
4. Native platform feature? → use it
5. Installed dependency? → use it
6. One line? → one line
7. Only then: the minimum that works
