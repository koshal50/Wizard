# Runtime Engine

This document describes the Wizard Runtime Engine — what it is, what each of its internal subsystems does, and how they work together with the two-graph architecture.

---

## What the Runtime Engine Is

The Runtime Engine is the core of Wizard. Every important operation passes through it. It manages the complete investigation lifecycle, maintains both graphs, executes all verification logic, and produces the final report.

The Runtime Engine is intentionally deterministic. Given the same repository and the same sequence of observations, it will always produce the same conclusions. This makes investigations reproducible, explainable, and independently testable.

The Runtime Engine is not intelligent. It does not reason about what a repository means. That is the job of the Investigation Planner and the AI agents. The Runtime Engine's job is coordination, execution, verification, and state management.

---

## The Two Graphs That Live Inside the Runtime Engine

The Runtime Engine owns and maintains two graphs for every investigation.

### Knowledge Graph

The Knowledge Graph stores what the Runtime Engine has learned about the repository.

Every node is a **Claim** — a validated, evidence-backed fact about the repository. Every edge is a **Relationship** between claims (DEPENDS_ON, USES, CONTRADICTS, PROVIDES, etc.).

The Knowledge Graph is the Runtime's long-term memory of the repository. It answers: **what do we know?**

Claims enter the Knowledge Graph only through the Evidence Engine after passing validation. The Planner and agents cannot insert claims directly. This is a hard architectural invariant.

### Investigation Graph

The Investigation Graph stores the investigation's execution path.

Every node is an **Investigation Node** — a unit of work (read a file, run a command, verify a claim, call the Planner). Every edge represents a dependency between nodes.

The Investigation Graph answers: **how are we getting there?**

Investigation Nodes are created dynamically by the Investigation Planner. The graph starts with the root goal and grows as the investigation proceeds. Every node that has run is stored permanently as part of the investigation history.

The two graphs reference each other. Investigation Nodes produce Claims that enter the Knowledge Graph. Knowledge Graph state informs the Planner when creating Investigation Nodes.

---

## The 14 Subsystems

The Runtime Engine is composed of 14 subsystems. Each owns exactly one responsibility.

```
                    Runtime Kernel
                          │
     ┌────────────────────┼────────────────────┐
     │                    │                    │
     ▼                    ▼                    ▼
Investigation Manager  Event Bus      Investigation Planner
     │
     ├── Repository Manager
     │       └── Fast Scanner
     │
     ├── Sandbox Manager
     │       └── Tool Runtime
     │
     ├── Observation Engine
     │
     ├── Extractor Framework
     │
     ├── Evidence Engine
     │
     ├── Knowledge Graph
     │
     ├── Investigation Graph
     │
     ├── Trust Engine
     │
     ├── Goal Engine
     │
     ├── Priority Engine
     │
     └── Report Generator
```

---

## Runtime Kernel

The Runtime Kernel is the central coordinator. It brings all other subsystems online, routes Investigation Requests, manages lifecycle transitions, and dispatches events.

The Kernel does not perform analysis. It manages coordination.

---

## Investigation Manager

The Investigation Manager creates and owns every active Investigation. It initializes both graphs, manages the investigation budget, tracks the current lifecycle state, and coordinates completion.

The Investigation Manager is the single source of truth for what investigations exist and what state they are in.

---

## Repository Manager

The Repository Manager loads the repository and provides controlled, stable access to its contents. It manages repository paths, creates temporary working directories, and provides repository metadata.

### Fast Scanner

The Fast Scanner is a subsystem of the Repository Manager. It performs the first operation of every investigation: a lightweight scan that produces the Repository Manifest.

The Fast Scanner reads **only metadata**:
- Complete directory tree (file names and paths only)
- File extensions
- File sizes
- Presence of well-known signal files

No file contents are read by the Fast Scanner. It is deliberately cheap — typically completing in under one second even for large repositories.

The Repository Manifest produced by the Fast Scanner is what the Investigation Planner receives for its initial planning call. It is typically 200 to 500 tokens — compact enough for an LLM call without overwhelming the context window.

---

## Sandbox Manager

The Sandbox Manager creates isolated execution environments. Every repository interaction happens inside a Sandbox. Repositories are treated as untrusted.

The Sandbox enforces resource limits (CPU, memory, disk, network) and captures all outputs. After execution, the Sandbox is destroyed completely.

---

## Tool Runtime

The Tool Runtime executes operations inside the Sandbox. Every Investigation Node that requires an action against the repository goes through the Tool Runtime.

Every tool follows the same interface: accept parameters, execute one operation, return a standardized response. Examples: Read File, Execute Command, Search Repository, Check Network Port.

Tool failures are not system errors. They become Observations. A command that exits with a non-zero code is informative evidence about the repository, not a bug in Wizard.

---

## Observation Engine

The Observation Engine stores every observation generated during an investigation. Observations are immutable. Once created, they cannot be changed.

Every Observation contains:
- A unique Observation ID
- A timestamp
- The source (which Investigation Node produced it)
- The observation type
- The raw payload
- The repository path it relates to
- The Investigation ID
- The Investigation Node ID that created it

This last field — the Investigation Node ID — is what connects the Observation Store to the Investigation Graph. Every conclusion can be traced back to an observation, and every observation back to the specific graph node that triggered it.

---

## Investigation Graph

The Investigation Graph is a first-class subsystem of the Runtime Engine. It stores, manages, and traverses the investigation's execution path.

Responsibilities:
- Storing every Investigation Node that has been created
- Tracking node states (waiting, running, complete, failed, blocked)
- Tracking node dependencies (this node requires that node's output)
- Recording which Observations and Claims each node produced
- Making the graph queryable by the Priority Engine and Planner
- Persisting the graph for post-investigation audit

An Investigation Node contains:
- Node ID
- Node type (Discovery, Read, Execute, Parse, Verify, Synthesize, Planner, Checkpoint)
- Action specification
- Hypothesis (what the Planner expected to find)
- Success claim template (claim to create if hypothesis is confirmed)
- Failure claim template (claim to create if hypothesis is refuted)
- Escalation condition (what unexpected output triggers a Planner consultation)
- Parent node ID
- Dependency node IDs
- State
- Execution timestamp
- Observations produced
- Claims produced

The hypothesis field is what allows the Runtime Engine to evaluate most node outcomes deterministically, without consulting the LLM. Expected outcomes map to predefined claim templates. Only unexpected outcomes escalate to the Planner.

---

## Extractor Framework

The Extractor Framework converts raw Observations into structured Claims.

**Deterministic Extractors** parse structured data (JSON, YAML, Dockerfiles, exit codes, port responses). They do not use AI. They always produce the same output for the same input.

**Cognitive Extractors** use an LLM to extract meaning from ambiguous or unstructured data. Used only when deterministic extraction is insufficient.

The Extractor Framework also validates every proposed Claim before it enters the Evidence Engine. Invalid Claims are rejected before they can enter the Knowledge Graph.

---

## Evidence Engine

The Evidence Engine links Observations to Claims.

Evidence answers the question: "Why does the Runtime Engine believe this Claim?"

Every Claim must have at least one piece of Evidence. Evidence is created by connecting one or more Observations to one Claim, along with the source's reliability score.

Evidence can be supporting (strengthens belief in the Claim) or contradictory (weakens it). The Evidence Engine prevents the same observation from being counted as multiple independent pieces of evidence — a critical protection against artificially inflated trust.

---

## Knowledge Graph

The Knowledge Graph subsystem stores and manages the growing model of repository knowledge.

Every node is a Claim. Every edge is a typed relationship between Claims. The graph starts empty and grows as evidence accumulates.

Responsibilities:
- Storing validated Claims as graph nodes
- Creating and managing relationships between Claims
- Making the graph searchable and traversable
- Providing the current Knowledge Graph state to the Planner (in summarized form) for ongoing planning calls

---

## Trust Engine

The Trust Engine computes and maintains the trust level for every Claim.

Trust is calculated by the Runtime Engine — not by the Planner or the agents. It considers:

- How many independent observations support the Claim
- Source reliability (execution result > config file > documentation)
- Whether contradictory evidence exists
- Graph relationships to other trusted Claims

Trust propagates through the Knowledge Graph. If a Claim's trust changes significantly, dependent Claims are also updated.

Contradictions are not errors. They are important information. When two Claims contradict each other, both are stored. The Trust Engine records the contradiction and the final report clearly documents it.

---

## Goal Engine

The Goal Engine manages the investigation's objectives.

Goals come from the Technology Plan produced by the Investigation Planner. Goals can also be created dynamically mid-investigation if the Planner determines that something new needs to be verified.

Goals are represented in the Investigation Graph as Checkpoint Nodes. A Checkpoint Node is marked satisfied when:
- All required Claims for that goal are present in the Knowledge Graph
- Those Claims have sufficient trust
- No unresolved critical contradictions remain

---

## Priority Engine

The Priority Engine decides which Investigation Node should be executed next.

It considers:
- Which nodes have all dependencies satisfied (eligible to run)
- Which active Checkpoint Node has the most urgent evidence gap
- How much budget remains
- Whether previous executions have already tried this path without success

The Priority Engine does not call the LLM. It is a deterministic scheduler. The investigation's order of execution is determined by evidence gaps and goal priority, not by AI reasoning.

---

## Report Generator

The Report Generator assembles the final Verification Report when the investigation converges.

It reads from:
- The Knowledge Graph (all verified Claims with trust levels)
- The Investigation Graph (the complete execution audit trail)
- The Observation Engine (raw evidence for specific claims)
- The Goal Engine (which goals completed, which failed, which are partially verified)

The Report Generator never invents information. Every statement in the report is backed by Claims from the Knowledge Graph. Every Claim references the Investigation Graph node that produced it. Every node references the Observations that triggered it.

The full audit trail is intact. The report is not a summary — it is a structured window into verified knowledge.

---

## The Runtime Engine Is Technology Neutral

The Runtime Engine knows nothing about Node.js, Docker, Python, or any other specific technology.

- It does not know that `package.json` signals Node.js
- It does not know what `npm install` does
- It does not know what "Framework = Express" means

All of that understanding comes from the Investigation Planner. The Runtime Engine receives structured Investigation Nodes with hypotheses and claim templates. It executes them, evaluates outcomes, and stores results. The meaning of those results is encoded in the node's hypothesis and claim templates — produced by the Planner, not hardcoded in the Runtime.

This means the Runtime Engine never needs to change when new technologies emerge. Only the Planner (which is backed by an LLM) needs to understand new technologies.

---

## Implementation Order for Shivam

1. Runtime Kernel
2. Investigation Manager
3. Repository Manager + Fast Scanner
4. Tool Runtime + Sandbox Manager
5. Observation Engine
6. Event Bus
7. Investigation Graph (the new subsystem, critical)
8. Extractor Framework
9. Evidence Engine
10. Knowledge Graph
11. Trust Engine
12. Goal Engine
13. Priority Engine
14. Investigation Planner integration (coordinate with Yash)
15. Report Generator

Build Investigation Graph early — it is the backbone of the new architecture. Everything else depends on it.
