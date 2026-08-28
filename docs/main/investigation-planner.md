# Investigation Planner

This document explains the Investigation Planner — the component that replaced the static Knowledge Module system. It explains what the Planner does, why the old approach was abandoned, how the Planner interacts with the two-graph architecture, and what "progressive context" means in practice.

---

## Why the Static Knowledge Module Approach Was Dropped

The original design had a Knowledge Registry with hardcoded modules — one for Node.js, one for Docker, one for Python, and so on. Every new technology would require a developer to write a new module.

This creates a fundamental problem. The investigation system's ability to understand a repository is limited by what modules have been written. A repository using Bun, Deno, Astro, LangGraph, Temporal, or Zig — technologies that did not exist when Wizard was built — would simply not be understood.

Beyond that, the distinction between "which module handles this file" and "what does this file tell us about the system" requires human knowledge to encode. But LLMs already have that knowledge, and they have it for thousands of technologies. The question is not whether to use LLMs for technology understanding. The question is how to use them correctly without abandoning determinism and reliability.

The answer is the Investigation Planner.

---

## What the Investigation Planner Is

The Investigation Planner is an LLM-powered component that generates dynamic investigation plans from repository context.

Instead of the Runtime asking:

> "Which hardcoded plugin handles this file?"

The Planner asks the LLM:

> "Given what we know about this repository so far, what should we investigate next, what do we expect to find, and what claim would that produce?"

The Planner does not replace the Runtime. The Runtime is still fully deterministic. The Planner only operates in the planning phase — it decides what investigation steps should exist and what they should look for. The Runtime executes those steps deterministically.

---

## The Progressive Context Strategy

The Planner never receives the entire repository. This would be:

- Too expensive in tokens
- Too slow in latency
- Wasteful, since most of a repository is irrelevant to most investigation goals
- Limited by context window size on large codebases

Instead, context is built progressively in three tiers.

### Tier 1: Repository Manifest

The Runtime performs a fast, cheap scan that collects only metadata — no file contents.

The Repository Manifest contains:

- The directory tree (file names and paths)
- File extensions (language signals)
- File sizes
- Presence of well-known key files (`package.json`, `Dockerfile`, `.github/`, etc.)

This takes milliseconds and produces a compact summary, typically 200 to 500 tokens.

Example manifest:

```
Repository: my-project
Files: 147 files across 23 directories

Key files detected:
  package.json     (2.1KB)
  Dockerfile       (0.8KB)
  docker-compose.yml (1.2KB)
  .github/workflows/main.yml (0.6KB)
  src/             (89 files, mostly .ts)
  README.md        (8.4KB)
  .env.example     (0.1KB)

Dominant extensions: .ts (63), .json (12), .yml (8), .md (4)
```

This manifest is what the Planner receives for its initial planning call.

### Tier 2: Targeted File Reads

When the Planner or the Investigation Graph requires the contents of a specific file, only that file is read. The Runtime reads it and makes it available as an Observation.

For example, if the Planner determines that understanding the Node.js entry point requires reading `package.json`, the Runtime reads `package.json` and provides it. The Planner never receives the entire source tree — just the files that matter for the current investigation step.

### Tier 3: Execution Results

When a command is executed — `npm install`, `docker build`, `python -m pytest` — the output becomes an Observation. The Planner can reason about these outputs to determine what to investigate next.

This three-tier approach keeps LLM context small and targeted throughout the investigation. The Planner only ever sees what is relevant to its current decision.

---

## What the Planner Produces

The Planner produces two things for every investigation.

### 1. The Initial Technology Plan

At the start of an investigation, after receiving the Repository Manifest, the Planner produces a Technology Plan. This is a structured JSON document describing what technologies appear to be present and what goals should be created.

Example:

```json
{
  "technologies": [
    {
      "name": "Node.js",
      "confidence": "high",
      "signals": ["package.json", "src/*.ts"],
      "initial_goals": ["Verify Runtime", "Verify Dependencies"],
      "key_files": ["package.json", "tsconfig.json"]
    },
    {
      "name": "Docker",
      "confidence": "high",
      "signals": ["Dockerfile", "docker-compose.yml"],
      "initial_goals": ["Verify Docker Build", "Verify Container Runtime"],
      "key_files": ["Dockerfile", "docker-compose.yml"]
    },
    {
      "name": "GitHub Actions",
      "confidence": "medium",
      "signals": [".github/workflows/main.yml"],
      "initial_goals": ["Verify CI Configuration"],
      "key_files": [".github/workflows/main.yml"]
    }
  ]
}
```

The Runtime uses this Technology Plan to generate the initial Goal set. The Technology Plan is generated once per investigation. It can be extended dynamically if new technologies are discovered mid-investigation.

### 2. Investigation Nodes (ongoing)

Throughout the investigation loop, the Planner creates Investigation Nodes one at a time. This is described in detail in the Investigation Graph section below.

---

## The Two-Graph Architecture

Wizard maintains two separate graphs during every investigation.

### Graph 1: Knowledge Graph

The Knowledge Graph stores what the Runtime has learned about the repository.

Every node is a **Claim** — a structured fact about the repository. Every edge is a **Relationship** between claims.

Examples of nodes: "Runtime = Node.js 18", "Framework = Express 4.18", "Container = Docker"
Examples of edges: "Framework DEPENDS_ON Runtime", "Container USES Runtime"

The Knowledge Graph starts empty and grows as evidence is collected and validated. It is the Runtime's answer to the question: **what do we know?**

This graph is deterministic. Claims enter it only after passing the Evidence Engine and Trust Engine. The LLM cannot insert claims directly.

### Graph 2: Investigation Graph

The Investigation Graph stores how the investigation is proceeding. It is a directed graph of **Investigation Nodes** — units of work.

Each node represents one step in the investigation: reading a file, executing a command, verifying a specific claim, or making a planning decision.

The Investigation Graph starts with one node: the root goal (for example, "Verify Runtime"). New nodes are added dynamically as the investigation progresses. The graph literally grows as the investigation runs.

This graph is the Runtime's answer to the question: **how are we getting there?**

Unlike the Knowledge Graph, the Investigation Graph records the investigation's execution path. It makes every decision traceable. It tells you not just what was found, but exactly how it was found and in what order.

---

## Investigation Nodes in Detail

An Investigation Node is a single unit of work in the Investigation Graph.

Every Investigation Node has:

- **A node ID** (unique within the investigation)
- **A node type** (one of the types below)
- **An action** (what the Runtime should do)
- **A hypothesis** (what the Planner expects to find)
- **A success claim** (what claim to create if the hypothesis is confirmed)
- **A failure claim** (what claim to create if the hypothesis is refuted)
- **A parent node ID** (which node generated this one)
- **Dependencies** (which other nodes must complete before this one runs)

### Node Types

| Type | Purpose |
|---|---|
| **Discovery Node** | Reads repository metadata or scans for files matching a pattern |
| **Read Node** | Reads the full contents of a specific file |
| **Execute Node** | Runs a command inside the sandbox |
| **Parse Node** | Extracts structured information from a previously read file |
| **Verify Node** | Tests a specific claim against evidence |
| **Synthesize Node** | Combines multiple observations into a single claim |
| **Planner Node** | Calls the LLM Planner to determine what nodes to create next |
| **Checkpoint Node** | Evaluates whether a goal has been satisfied |

### The Hypothesis Field

This is the most important part of an Investigation Node — and the key addition beyond what other dynamic graph systems do.

When the Planner creates an Investigation Node, it also declares what it expects the node to produce. This is the hypothesis.

Example:

```json
{
  "node_id": "node_014",
  "type": "ExecuteNode",
  "action": {
    "command": "npm install",
    "working_directory": "/"
  },
  "hypothesis": "All dependencies install without errors",
  "success_claim": {
    "type": "DEPENDENCY_HEALTH",
    "value": "installable",
    "trust_weight": 0.85
  },
  "failure_claim": {
    "type": "DEPENDENCY_HEALTH",
    "value": "broken",
    "trust_weight": 0.90
  },
  "unexpected_action": "escalate_to_planner"
}
```

The hypothesis field transforms the Runtime from a passive recorder into an active verifier. When the node executes:

- If `npm install` exits with code 0 → the Runtime creates the success claim deterministically, with no LLM call
- If `npm install` exits with a non-zero code → the Runtime creates the failure claim deterministically, with no LLM call
- If something unexpected happens (the package manager is not npm, or the project uses workspaces, or the output is ambiguous) → the Runtime escalates to the Planner for interpretation

This design dramatically reduces the number of LLM calls. The Planner is called to create nodes. The Runtime evaluates expected outcomes deterministically. The Planner is only re-consulted when something unexpected happens. In practice, this means most investigations complete with far fewer LLM calls than a naive "ask the LLM after every tool execution" approach.

---

## How the Investigation Graph Grows

Let us trace through an example. The user runs `wizard verify runtime` on a Node.js repository.

**Step 1:** The Runtime creates the root node: `Checkpoint Node — Verify Runtime [unsatisfied]`

**Step 2:** The Runtime calls the Planner. The Planner receives the Repository Manifest and the root goal. The Planner creates the first Investigation Nodes:

```
Checkpoint Node: Verify Runtime
├── Read Node: package.json
│     hypothesis: contains scripts.start field
└── Discovery Node: scan for entry point files
      hypothesis: finds index.js or server.js or app.js
```

**Step 3:** The Runtime executes the Read Node. It reads `package.json`. The output becomes an Observation. The hypothesis is evaluated: `scripts.start` exists (`"start": "node server.js"`). The success claim is created: "Entry Point = server.js". No LLM call needed for this evaluation.

**Step 4:** The Planner creates the next nodes based on the updated graph state:

```
Read Node: package.json [complete]
├── Parse Node: extract all dependencies
│     hypothesis: finds Express, dotenv, mongoose
├── Execute Node: npm install
│     hypothesis: installs without errors
└── Execute Node: node server.js
      hypothesis: starts on port 3000
      depends_on: [npm install node]
```

**Step 5:** npm install runs. Exit code 0. Success claim created deterministically: "Dependencies = installable." Trust updated.

**Step 6:** node server.js runs. Port 3000 becomes active. HTTP GET returns 200. Execution claim created: "Runtime = verified, port 3000 responsive."

**Step 7:** The Checkpoint Node evaluates: all required claims for "Verify Runtime" are now satisfied with sufficient trust. Goal complete.

The Investigation Graph at the end looks like:

```
Checkpoint: Verify Runtime [satisfied]
├── Read: package.json [complete]
│   ├── Parse: dependencies [complete] → Claims created
│   ├── Execute: npm install [complete] → Dependency claim
│   └── Execute: node server.js [complete] → Runtime verified
└── Discovery: entry point files [complete]
```

Every node is stored permanently. Every claim in the Knowledge Graph can be traced to the Investigation Graph node that produced it. Every Investigation Graph node can be traced to the Observation that triggered it.

---

## The Planner's Input Format

Every time the Planner is called to create the next node (or nodes), it receives a compact summary of the current investigation state. This summary includes:

**Current goal:** What the investigation is trying to verify right now

**Knowledge Graph state (summarized):** What has been learned so far — not the full graph, just the claims relevant to the current goal

**Investigation Graph state (recent):** The last 3 to 5 nodes that have completed, and their outcomes

**Open questions:** What gaps remain in the evidence — specifically, what claims are still needed to satisfy the active goal

**Repository context (incremental):** Only the file contents or execution outputs that have been read so far

The Planner never receives the entire investigation history. It only receives what is relevant to the next decision. This keeps token usage low throughout even long investigations.

---

## What the Planner Cannot Do

The Planner is a planning component. It is not a verification component.

The Planner cannot:
- Insert claims directly into the Knowledge Graph
- Mark goals as complete
- Set trust values
- Modify Observations
- Access the repository directly

Everything the Planner decides becomes a structured request to the Runtime. The Runtime validates the request, executes it, and produces structured results. The Planner's influence on the investigation is always mediated through the Runtime.

This constraint preserves the core architectural principle: the Runtime owns truth. The Planner informs the investigation. The Runtime verifies it.

---

## What the Investigation Planner Contributor (Yash) Owns

Yash is responsible for the entire Investigation Planner subsystem.

This includes:
- Designing the Repository Manifest format
- Implementing the Fast Scanner that produces the manifest
- Designing the Technology Plan format
- Writing the system prompts for the initial planning call
- Designing the Investigation Node format (all node types, the hypothesis field, the success/failure claim structure)
- Writing the ongoing planning prompts (the prompts used when the Planner is called during the investigation loop)
- Defining the escalation conditions (when does the Runtime escalate to the Planner vs. handling a result deterministically)
- Coordinating with Shivam on how the Planner integrates with the Investigation Graph in the Runtime Engine

**Tech stack: prompt engineering + data format design.** The LLM provider is a free, self-hosted **open-source model served through vLLM's OpenAI-compatible `/v1/chat/completions` endpoint** — the same provider and `WIZARD_LLM_BASE_URL` / `WIZARD_LLM_MODEL` configuration used by the Agent System (`app/llm/vllm_provider.py`, selected via `get_llm_provider()`). Both subsystems therefore share one open-source model and one integration pattern; no paid API is used.

---

## Why This Is Better Than Static Knowledge Modules

| Dimension | Static Modules | Investigation Planner |
|---|---|---|
| New technologies | Require writing new code | Handled by LLM automatically |
| Technologies from after project launch | Not supported | Supported immediately |
| Investigation path | Predefined by module authors | Emerges dynamically from repository evidence |
| Number of LLM calls | Many (agent reasoning) | Minimal (planner creates nodes; Runtime evaluates most results deterministically) |
| Repo context sent to LLM | N/A (no LLM in modules) | Only metadata and targeted files (never full repo) |
| Auditability | No record of module decisions | Full Investigation Graph shows every decision |
| Extensibility | Add a new module file | No change needed for new technologies |
| Correctness | Depends on module quality | Depends on Runtime's deterministic evaluation + hypothesis verification |
