# Wizard — Architecture

LLM-powered **Investigation Planner** running inside a deterministic **Runtime**,
built on a **two-graph** design.

> **The Runtime owns truth. The Planner only informs the investigation.**

This document describes how the system is put together, why the boundaries sit
where they do, and where each responsibility lives in the source tree. Every
statement here reflects the code as it actually is — not an aspiration.

---

## 1. The core idea: two graphs, one owner

The system keeps two completely separate graphs and never merges them:

| | **Knowledge Graph** | **Investigation Graph** |
|---|---|---|
| Answers | *What do we know?* | *How did we find it?* |
| Nodes | `Claim`s (+ relationships) | `InvestigationNode`s (+ edges) |
| Owner | Runtime (via the Evidence/Trust engines) | Runtime (materialised from Planner proposals) |
| Trust | Yes — computed from evidence | **Never** — nodes carry no trust/evidence |
| Mutability | `Claim` is append-evidence; value/trust recomputed | node status advances; observations immutable |

The separation is enforced at the **type level** (`src/core/types.ts`): a
`Claim` cannot appear inside the Investigation Graph and an `InvestigationNode`
cannot carry trust. The end-to-end test `tests/endToEnd.test.ts` pins this
invariant ("the two graphs stay separate: no claim leaks into the investigation
graph").

### Why two graphs?

Because *knowledge* and *the process of acquiring knowledge* have different
lifecycles and different trust semantics. A claim can be corroborated or
contradicted by many nodes over time; a node is a single, immutable act of
investigation. Fusing them would make it impossible to answer "why do we believe
this?" independently of "what did we try?".

---

## 2. The Planner ↔ Runtime boundary (the security seam)

This is the most important boundary in the system.

```
        proposals only                materialises + owns truth
  ┌────────────────────┐   ────────►  ┌──────────────────────────┐
  │   Planner (LLM)    │              │   Runtime (deterministic) │
  │  "what to look at" │   ◄────────  │  "what is actually true"  │
  └────────────────────┘   context    └──────────────────────────┘
```

The Planner **may only return proposals**:

- `TechnologyPlan` — an initial guess at technologies + goals, and
- `PlannerNodeProposal` batches — suggested next nodes.

A `PlannerNodeProposal` (`src/core/types.ts`) is deliberately a *subset* of
`InvestigationNode`: it has **no** `status`, `createdAt`, `observationId`, trust,
or evidence. Those are runtime-owned. The Runtime **materialises** each accepted
proposal into a real node, stamping the runtime-owned fields itself.

The Planner **must not, and structurally cannot**:

- read repository files directly,
- execute shell commands,
- write to the Knowledge Graph or insert claims,
- create observations,
- assign final trust, or
- mark a goal complete.

Every one of those is a Runtime capability. The Planner only ever sees a
**compact, curated context** (`PlannerContext`) and returns **data that is
validated before the Runtime accepts it** (`src/planner/PlannerValidator.ts`).

### Validation gate

Nothing the Planner emits is trusted. `PlannerValidator` (exercised by
`tests/plannerValidator.test.ts` and `tests/schema.test.ts`) enforces:

1. **Schema shape** — via `src/planner/schemas.ts`, which uses
   `object(..., {allowUnknownKeys:false})` so a proposal that smuggles a
   runtime-owned field (`status`, `createdAt`, `observationId`, `trust`) is
   **rejected**, not silently stripped.
2. **Type/action agreement** — a node whose `type` disagrees with its
   `action.type` discriminator is rejected.
3. **Path confinement** — `read`/`discovery` targets are resolved with
   `resolveInsideRepo` and rejected if they escape the repo, are absolute, or
   contain a null byte.
4. **Command safety** — `execute` commands pass `checkCommandSafety`
   (allowlist + dangerous-pattern denylist); unsafe commands are dropped.
5. **Execution policy** — when execution is disabled, `execute` proposals are
   rejected outright.
6. **Budget** — a batch is truncated to the remaining node budget.

The valid subset is kept; the rest is discarded with a logged reason. A partly
bad batch never fails the whole investigation.

---

## 3. Lifecycle

The Runtime drives a state machine (`src/runtime/RuntimeEngine.ts`):

```
created → scanning → planning → investigating → converging → reporting → completed
                                                                    ↘ cancelled / failed
```

End-to-end flow:

```
 Request
   │
   ▼
 Scanner ─────────────► fast repo scan (files, sizes)          src/scanner/fastScanner.ts
   │
   ▼
 Manifest ────────────► normalise scan → RepositoryManifest    src/manifest/
   │
   ▼
 Technology Plan ─────► Planner.planTechnologies(manifest)     src/planner/TechnologyPlanner.ts
   │                    (heuristic/LLM) → detected techs + goals
   ▼
 Goals ───────────────► buildGoal(...) per tech, filtered by   src/runtime/goalTemplates.ts
   │                    the request's investigationTargets
   ▼
┌──────────────── main loop (investigate) ─────────────────────┐
│  refresh goal statuses from current knowledge                │
│  all goals resolved? ──► stop                                │
│  ready node? ──► pick highest priority ──► execute ──┐       │
│      │  PriorityEngine.pickNext          NodeRunner   │       │
│      │                                                ▼       │
│      │                                          Observation   │  (immutable)
│      │                                                │       │
│      │                                     ResultEvaluator    │  deterministic:
│      │                                                │       │  SUCCESS/FAILURE/UNEXPECTED
│      │                          ┌─── SUCCESS/FAILURE ─┤       │
│      │                          ▼                     │       │
│      │                    EvidenceEngine.recordClaim  │       │
│      │                    → Evidence → Trust → Claim   │       │
│      │                          │                     │       │
│      │                          ▼               UNEXPECTED?    │
│      │                    KnowledgeGraph        └► escalate    │  (only if the node says
│      │                                            to Planner   │   so AND budget remains)
│      │                                                         │
│  no ready node? ──► Planner.planNext(context) for an open goal │
│      │                └► validated batch ──► insert nodes       │
│  no progress possible? ──► goal unsatisfiable                  │
└───────────────────────────────────────────────────────────────┘
   │
   ▼
 Converge ────────────► any still-open goal → "unsatisfiable"   (never over-claims)
   │
   ▼
 Result ──────────────► InvestigationResult
   │
   ▼
 ReportGenerator ─────► verification_report.md + investigation.json (snapshot)
```

The loop is bounded on **three** independent ceilings so it always terminates:
node-execution budget, planner-call budget, and wall-clock time (plus a
`MAX_ITERATIONS` backstop and `MAX_PLAN_ATTEMPTS_PER_GOAL`).

### Minimise the LLM

A central design goal: **deterministic first, LLM only when genuinely stuck.**

- `ResultEvaluator.evaluateNode` classifies every result with **no LLM** — each
  node type has a fixed rule (`tests/resultEvaluator.test.ts`).
- Only an **UNEXPECTED** result can reach the Planner, and only when the node's
  `unexpectedAction` is `escalate_to_planner` *and* planner budget remains.
  `record_only` nodes never call the Planner.
- An `execute` node that could not run because execution is globally disabled is
  an *honest downgrade*, not a surprise: the Runtime records it and lets the goal
  be reported `unsatisfiable` rather than spending an LLM call or fabricating a
  result.

---

## 4. Node types

Eight node types (`InvestigationNodeType`), each with a discriminated `action`
(`src/core/types.ts`) and a leaf executor (`src/nodes/`, wired by
`src/nodes/registry.ts`):

| Type | Action fields | What it does | Produces observation |
|---|---|---|---|
| `discovery` | `pattern`, `directory?` | Find files matching a pattern | `discovery_result` |
| `read` | `filePath` | Read a file (confined to the repo) | `file_content` |
| `execute` | `command`, `workingDirectory?`, `timeoutMs?` | Run a **safety-checked** command | `command_result` |
| `parse` | `sourceObservationId`, `parser` | Parse a prior observation (e.g. `package.json`) | `parse_result` |
| `verify` | `claimId?`, `evidenceIds` | Cross-check evidence for a claim | `verify_result` |
| `synthesize` | `observationIds` | Combine observations into a conclusion | `synthesis_result` |
| `planner` | `reason` | An explicit request for Planner input | `planner_result` |
| `checkpoint` | `goalId` | Assess whether a goal is satisfied | `checkpoint_result` |

Each node also carries a `hypothesis` and optional `successClaim` /
`failureClaim` templates — the fact to record if the hypothesis holds or fails.

---

## 5. Observations (immutable evidence-in-the-raw)

Executing a node yields exactly one `Observation` (`src/observations/`), which is
**immutable** (`readonly` fields + `immutable: true`). Observations are the raw
record of what happened — file contents, command exit codes and output, parse
results. They are the *only* source from which claims may be built.

Observation types mirror node outputs: `file_content`, `command_result`,
`discovery_result`, `parse_result`, `verify_result`, `synthesis_result`,
`planner_result`, `checkpoint_result`, `error`.

---

## 6. Evidence → Trust → Claim

The only writer of claims is the **EvidenceEngine** (`src/evidence/EvidenceEngine.ts`).
When the evaluator selects a claim template, `recordClaim`:

1. Builds an `Evidence` entry from the producing observation, classified by
   **source kind** (`src/evidence/extractors.ts`).
2. Finds the existing canonical claim of that type, or creates one.
3. Appends the evidence (idempotent per observation — the same observation is
   never counted twice).
4. Recomputes the claim's **best-supported value** and **trust** deterministically.
5. Writes through to both the `ClaimStore` (identity) and the `KnowledgeGraph`
   (queryable view), materialising any relationship templates as edges.

### Source-kind weights

Evidence strength is ordered by *how directly it observed reality*
(`src/evidence/extractors.ts`):

| Source kind | Weight | Example |
|---|---:|---|
| `execution` | **0.90** | a command actually ran (`command_result`) |
| `structured_file` | **0.70** | parsed `package.json` / `Dockerfile` (`parse_result`, non-doc `file_content`) |
| `documentation` | **0.40** | README / `.md` prose |
| `inference` | **0.25** | derived / synthesised / everything else |

### Trust math

`computeTrust` (`src/trust/TrustEngine.ts`, tested by `tests/trust.test.ts`):

- Evidence for the **same** value combines by **noisy-OR**:
  `combined = 1 − Π(1 − wᵢ)` — corroboration rises toward, but never reaches, 1.
- Evidence for a **different** value is contradiction.
- `trust = support × (1 − contradiction)`, clamped to `[0, 1]`.

Status is derived from the evidence balance:

| Condition | `ClaimStatus` |
|---|---|
| no contradicting evidence | `asserted` |
| contradiction present, `support ≥ contradiction` | `contested` |
| contradiction present, `contradiction > support` | `refuted` |

Because the EvidenceEngine always adopts the **best-supported** value for a
claim, a two-way contest resolves to `contested` (the winning value's support is,
by construction, ≥ its contradiction) — it does not flip straight to `refuted`.
This subtlety is pinned in `tests/evidencePipeline.test.ts`.

### The Planner cannot set trust

A `ClaimTemplate` may carry a `trustWeight` **hint**. The Trust Engine
**ignores** it for the final score — it is recorded as evidence metadata only.
Trust is *earned from real observations*, never asserted by the Planner. Two
tests guard this (`tests/evidencePipeline.test.ts`: a 1.0 hint on parse evidence
still yields 0.70).

---

## 7. Goals

A `Goal` (`src/runtime/GoalEngine.ts`, `goalTemplates.ts`) is satisfied when its
`GoalRequirement`s are met by claims meeting a **minimum trust threshold**
(default 0.6, configurable). A requirement can demand a claim of a type with a
specific value, or with a value that is *not* something (e.g. runtime is not
`broken`).

Goal statuses: `waiting → in_progress → satisfied | unsatisfiable`. The Runtime
refreshes statuses from current knowledge before every scheduling decision, and
at convergence marks any still-open goal `unsatisfiable` so the report **never
over-claims success**.

---

## 8. LLM providers (provider-agnostic, offline by default)

The Planner talks to an `LLMProvider` interface (`src/llm/LLMProvider.ts`).
`createProviderFromEnv` (`src/llm/providerFactory.ts`) selects one:

| `LLM_PROVIDER` | Provider | Notes |
|---|---|---|
| `heuristic` *(default)* | `HeuristicLLMProvider` | **Offline, deterministic, zero-key, zero-network.** Dispatches on purpose (technology_plan / ongoing_plan / escalation). |
| `mock` | `MockLLMProvider` | For tests: `queueResponse` / `queueRaw` / `queueError`, `callCount`. |
| `anthropic` | `AnthropicLLMProvider` | Requires `ANTHROPIC_API_KEY`. |
| `openai` | `OpenAILLMProvider` | Requires `OPENAI_API_KEY`. |

If a hosted provider is requested but its key is absent, the factory **falls back
to heuristic with a warning** — it never crashes and never blocks on missing
credentials. The whole pipeline (scan → plan → investigate → report) therefore
runs with **no configuration at all**, which is exactly what the end-to-end test
and `pnpm demo` rely on.

---

## 9. Security model

The threats this system explicitly defends against, and where:

| Threat | Defence | Location |
|---|---|---|
| Path traversal / outside-repo access | `resolveInsideRepo` — normalises, rejects `..`, absolute, null-byte | `src/util/safety.ts`, `tests/safety.test.ts` |
| Dangerous commands | `checkCommandSafety` — leader allowlist + dangerous-pattern denylist (`rm -rf`, `curl | sh`, `git push`, …) | `src/util/safety.ts`, `tests/safety.test.ts` |
| Executing raw LLM output | **Never done.** Planner output is *proposals*, validated before use | `src/planner/PlannerValidator.ts` |
| Smuggled runtime-owned fields | Schemas reject unknown keys (`status`/`createdAt`/`observationId`/`trust`) | `src/planner/schemas.ts`, `tests/schema.test.ts` |
| Unbounded execution | Node/planner/time budgets + iteration ceiling | `src/runtime/RuntimeEngine.ts` |
| Secret leakage into the report | Report emits **summaries only**, never raw stdout/file contents | `src/report/ReportGenerator.ts`, `tests/report.test.ts` |
| Secret leakage into logs | Logger redacts; `.env` values never logged | `src/util/logger.ts`, `src/cli/wizard.ts` |
| Fabricated results when exec disabled | Honest downgrade → goal `unsatisfiable`, no claim invented | `src/runtime/RuntimeEngine.ts`, `tests/endToEnd.test.ts` |

The report's secret-safety is directly asserted: a planted
`SECRET_TOKEN_sk-must-not-appear` in command stdout must **not** appear in the
rendered Markdown (`tests/report.test.ts`). The JSON snapshot deliberately
contains full observations — it is a local, `.gitignore`d debug artifact, and the
tests only assert the *Markdown* is secret-free.

---

## 10. CLI

`src/cli/wizard.ts` is the **only** composition root — the single place that
wires concrete subsystems together. Everything below it (clock, ids, logger,
provider) is injectable, so the engine never touches argv, env, or a wall clock
directly and stays deterministic and testable.

```
provider (from env) → InvestigationPlanner → RuntimeEngine → result → ReportGenerator
```

### Usage

```bash
node src/cli/wizard.ts <intent> [targets...] <repositoryPath> [flags]
```

- `intent` — `investigate | verify | explain | report` (default `investigate`),
  optional first positional.
- `targets` — e.g. `runtime dependencies` (optional middle positionals).
- `repositoryPath` — **required, always the last positional.**

| Flag | Meaning | Default |
|---|---|---|
| `--provider <name>` | Override LLM provider | from env / `heuristic` |
| `--budget <n>` | Max node executions | 60 |
| `--planner-budget <n>` | Max planner calls | 25 |
| `--timeout <ms>` | Max execution time | 120000 |
| `--out <dir>` | Artifact directory | `<repo>/.wizard` |
| `--no-exec` | Disable command execution | execution on |
| `--no-persist` | Do not write report/snapshot | persist on |
| `--json` | Print a JSON summary instead of Markdown | Markdown |
| `--verbose` / `--quiet` | Log echo level | `warn` |
| `-h`, `--help` | Show usage | — |

Unknown flags are ignored rather than fatal. Value flags accept both
`--k v` and `--k=v` forms. (`tests/cli.test.ts`.)

### Exit codes

| Code | Meaning |
|---:|---|
| `0` | Success (or a non-`verify` intent). |
| `1` | A `verify` run finished but not all goals were satisfied — a useful CI/healthcheck signal. |
| `2` | The engine failed (crash / could not start). |

### Examples

```bash
node src/cli/wizard.ts verify runtime ./sample-repos/sample-node-project
node src/cli/wizard.ts investigate ./some/repo --no-exec --json
```

---

## 11. Environment variables

Read only by the CLI/provider factory; see `.env.example`. The CLI loads a local
`.env` best-effort (dependency-free) and never logs its values.

| Variable | Purpose |
|---|---|
| `LLM_PROVIDER` | `heuristic` (default) \| `mock` \| `anthropic` \| `openai` |
| `LLM_MODEL` | Provider-specific model id (ignored by heuristic/mock) |
| `ANTHROPIC_API_KEY` | Required only for the `anthropic` provider |
| `OPENAI_API_KEY` | Required only for the `openai` provider |
| `LLM_BASE_URL` / `LLM_MAX_TOKENS` / `LLM_TIMEOUT_MS` | Optional hosted-provider overrides |

No key is ever required to run: absent credentials fall back to `heuristic`.

---

## 12. Source map

```
src/
  core/types.ts           Single source of truth for all cross-module types + invariants
  scanner/                Fast repository scan
  manifest/               Scan → RepositoryManifest; technology detectors
  planner/                Planner (proposals only): technology + ongoing + escalation
    InvestigationPlanner.ts   Facade the Runtime calls
    TechnologyPlanner.ts      Initial technology plan
    OngoingPlanner.ts         Next-batch planning for an open goal
    EscalationPlanner.ts      UNEXPECTED-result handling
    PlannerValidator.ts       The validation gate (safety + schema + budget)
    schemas.ts                Strict, unknown-key-rejecting schemas
    PlannerContextBuilder.ts  Builds the compact, curated PlannerContext
    prompts.ts / contextTypes.ts
  llm/                    Provider-agnostic LLM layer
    LLMProvider.ts, providerFactory.ts, extractJson.ts
    providers/            Heuristic (offline default), Mock, Anthropic, OpenAI
  runtime/                The deterministic owner of truth
    RuntimeEngine.ts          Lifecycle state machine + main loop
    ResultEvaluator.ts        Deterministic SUCCESS/FAILURE/UNEXPECTED
    PriorityEngine.ts         Which ready node runs next
    NodeScheduler.ts          Readiness, proposal insertion
    NodeRunner.ts             Executes one node → Observation
    GoalEngine.ts, goalTemplates.ts   Goal satisfaction
    EscalationEngine.ts       Bridges UNEXPECTED → Planner
    ProcessCommandRunner.ts   Real / disabled command execution
  nodes/                  Leaf executors, one per node type + registry
  observations/           Immutable ObservationStore
  evidence/               EvidenceEngine (only claim writer) + extractors (source-kind)
  trust/                  TrustEngine (noisy-OR; ignores Planner hints)
  claims/                 ClaimStore (claim identity)
  graphs/                 InvestigationGraph + KnowledgeGraph (kept separate)
  report/                 ReportGenerator (secret-safe Markdown + JSON snapshot)
  validation/             Schema primitives
  util/                   ids, clock, logger (redacting), safety (path + command)
  cli/wizard.ts           The one composition root
```

---

## 13. Determinism & testing

- **Determinism is injected, not assumed.** `clock` and `ids` are dependencies;
  the default heuristic provider is deterministic. The same request yields the
  same ids, claims, and trust — asserted by `tests/endToEnd.test.ts` ("the run
  is reproducible").
- **Runtime.** Node runs the `.ts` sources directly (native type-stripping);
  the codebase uses **erasable syntax only** — no `enum`, `namespace`, or
  constructor parameter properties. Zero runtime dependencies.
- **Type safety.** `tsconfig.json` is `strict` with `noUncheckedIndexedAccess`.

```bash
pnpm typecheck   # tsc, noEmit
pnpm test        # node:test — unit + integration; runs fully offline
pnpm demo        # end-to-end investigation on the bundled sample repo
```

The suite (`tests/`) covers the trust math, safety primitives, the strict
schemas, the Planner validator, deterministic result evaluation, the full
evidence pipeline, the secret-safe report, CLI parsing/exit-codes, and a **real
end-to-end run** of the engine against `sample-repos/sample-node-project` using
the offline heuristic provider.

---

## 14. Extending the system

- **A new technology** → add a detector in `src/manifest/detectors.ts` and, if
  needed, a goal template in `src/runtime/goalTemplates.ts`. The heuristic
  provider and detectors are what make the offline path produce real claims.
- **A new node type** → add the action to the `NodeAction` union in
  `src/core/types.ts`, an executor in `src/nodes/`, register it in
  `src/nodes/registry.ts`, and add its rule to `ResultEvaluator`.
- **A new LLM backend** → implement `LLMProvider` and register it in
  `src/llm/providerFactory.ts`. Nothing else changes — the Planner is
  provider-agnostic.
- **A new evidence source** → extend `sourceKindForObservation` /
  `SOURCE_WEIGHT` in `src/evidence/extractors.ts`. Trust recomputes
  automatically.

Throughout, the rule that keeps the system honest is the same one it started
with: **the Planner proposes; the Runtime decides; trust is earned from
observations, never asserted.**
```
