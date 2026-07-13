# Wizard Contributor Guide

This is the primary reference for the four contributors building Wizard. Read this end to end before writing any code. Every design decision explained here matters. If you disagree with something, discuss it with the team before changing it.

---

## What Wizard Actually Is

Wizard is an autonomous software repository verification system.

When a developer encounters an unknown repository — AI-generated, inherited, or simply unfamiliar — they have to spend time just understanding it before they can do anything useful. What language does it use? How do you run it? Do the dependencies actually install? Is the documentation accurate?

Wizard automates this process. It investigates the repository the same way a skilled developer would, but does so autonomously and systematically. Every conclusion is backed by real evidence collected from the repository itself, verified through actual execution where possible.

---

## The Central Idea: Evidence Driven Belief

Think about how a scientist works.

A scientist forms a hypothesis. They run an experiment. They observe the result. They update their belief based on what they observed. If a new experiment contradicts a previous belief, they revise it. They never publish a conclusion without showing the evidence.

Wizard works exactly the same way.

When Wizard investigates a repository, it forms hypotheses (called **Claims**), gathers evidence (called **Observations**), evaluates how trustworthy each claim is (called **Trust**), and only concludes when the evidence is sufficient.

The final output is a **Verification Report** — a document that explains everything Wizard found, what evidence supports each finding, and what remains uncertain.

---

## The Biggest Architectural Idea: Two Graphs

Wizard maintains two separate graphs during every investigation.

### Knowledge Graph — What We Know

The Knowledge Graph stores validated facts about the repository. Every node is a **Claim**. Every edge is a **Relationship** between Claims.

Examples:
- Node: "Runtime = Node.js 18"
- Node: "Framework = Express 4.18"
- Edge: "Framework DEPENDS_ON Runtime"

The Knowledge Graph answers: **what do we know about this repository?**

It starts empty and grows as evidence is collected and validated. The Planner and agents cannot insert claims directly — Claims enter only through the Evidence Engine.

### Investigation Graph — How We Got There

The Investigation Graph stores the investigation's execution path. Every node is an **Investigation Node** — a unit of work. Every edge represents a dependency between nodes.

Examples:
- Node: "Read package.json" → produced Claim "Runtime = Node.js 18"
- Node: "Execute npm install" → produced Claim "Dependencies = installable"
- Node: "Execute node server.js" → produced Claim "Runtime = verified"

The Investigation Graph answers: **how did we get to what we know?**

It starts with the root goal and grows dynamically as the investigation proceeds. Every node carries a **Hypothesis** — what the Planner expected to find — so that the Runtime Engine can evaluate most outcomes deterministically.

The two graphs reference each other. Investigation Nodes produce Claims that enter the Knowledge Graph. The Knowledge Graph state informs the Planner when creating new Investigation Nodes.

---

## Why the Knowledge Graph Alone Is Not Enough

The Knowledge Graph stores what is known. But without the Investigation Graph, you cannot answer:

- In what order were things discovered?
- Which file produced which claim?
- Why did the investigation go in this direction?
- Which Observation supports which Claim?
- When a claim is challenged, what evidence trail leads back to it?

The Investigation Graph is the complete audit trail of the investigation. It is what makes every conclusion fully explainable — not just "we believe this" but "we believe this because node_014 ran `npm install` and exit code 0 confirmed that dependencies install successfully, and that node was created because the initial Technology Plan identified Node.js and prioritized dependency verification."

---

## The Investigation Planner: Replacing Static Knowledge Modules

The original design had hardcoded Knowledge Modules — one for Node.js, one for Docker, and so on. Every new technology would require writing new code.

This was replaced with the **Investigation Planner**, an LLM-powered component that generates investigation plans dynamically for any repository and any technology.

### The Three Choices

There were three possible design approaches:

**Option 1: Hardcoded plugins.** Write a module for every technology. Predictable, fast, but breaks with every new framework and requires constant maintenance.

**Option 2: Pure LLM.** Ask the LLM everything. Completely flexible, but loses all reliability guarantees. The LLM becomes the source of truth, which means hallucinations become facts.

**Option 3 (what Wizard uses): LLM for planning, Runtime for verification.** The LLM plans the investigation. The Runtime Engine verifies the results. The LLM's job is to decide what Investigation Nodes to create. The Runtime Engine's job is to execute them and evaluate outcomes deterministically.

This preserves everything that makes the Runtime Engine reliable — deterministic verification, immutable observations, evidence-backed claims, computed trust — while removing the constraint that investigation planning must be hardcoded.

### Progressive Context: Never Send the Whole Repository

The Planner never receives the entire repository. This would be expensive, slow, and unnecessary.

Instead, context is built progressively in three tiers:

**Tier 1 — Repository Manifest (fast scan):** File names, directory tree, extensions, sizes. No contents. ~200–500 tokens. This is what the Planner receives for its initial call.

**Tier 2 — Targeted file reads:** When an Investigation Node requires reading a file, that file is read and made available. One file at a time. Only when needed.

**Tier 3 — Execution results:** Command outputs become Observations and are summarized for Planner context when needed.

### The Hypothesis Field: Minimizing LLM Calls

Every Investigation Node the Planner creates carries a **Hypothesis** — what it expects to find. The Runtime Engine uses this to evaluate outcomes without calling the LLM:

- Expected outcome (success or failure) → Runtime creates the appropriate Claim deterministically. No LLM call.
- Unexpected outcome → Runtime escalates to the Planner.

In practice, most node outcomes are expected. The Planner is consulted far less often during the investigation loop than at the start. This keeps the system fast and cost-efficient without sacrificing adaptability.

---

## The Two AI Agents

Wizard uses two AI agents built in **n8n**. These are separate from the Investigation Planner — the Planner generates structured investigation plans, while the agents provide deeper reasoning for complex, ambiguous situations.

### Explorer Agent

The Explorer Agent handles scenarios where the Planner's structured approach is insufficient. When the investigation encounters something that cannot be resolved through hypothesis-based nodes — a complex architectural pattern, a highly unusual repository structure, deeply ambiguous code — the Explorer Agent is invoked to reason about it.

The Explorer Agent does not create Investigation Nodes. It provides reasoning that the Planner uses to create better nodes.

### Verification Agent

The Verification Agent reviews conclusions before the investigation moves on from a topic. It looks for weak evidence, unresolved contradictions, and logical inconsistencies. It returns a structured assessment that the Runtime Engine uses to decide whether additional investigation is needed.

Both agents communicate with the Runtime Engine through a stable API. They never modify either graph directly.

---

## The Four CLI Commands

### investigate

```bash
wizard investigate <target>
```

Explores a specific aspect of the repository. Focus is on understanding, not pass/fail.

```bash
wizard investigate architecture
wizard investigate runtime
wizard investigate deployment
```

### verify

```bash
wizard verify <target>
```

Verifies whether a specific aspect of the repository works correctly. Continues until it can produce a confident verdict.

```bash
wizard verify runtime
wizard verify dependencies
wizard verify containers
wizard verify ci
```

### report

```bash
wizard report
```

Generates the Verification Report from verified knowledge. Saved as `verification_report.md`.

### explain

```bash
wizard explain <target>
```

Generates a human-readable explanation of something already verified. Does not trigger aggressive new investigation.

```bash
wizard explain architecture
wizard explain dependencies
```

---

## How Every Command Uses the Same Architecture

There are no separate code paths for different commands. Every command creates an Investigation Request with a different intent. The Runtime Engine processes all intents through the same two-graph architecture.

`wizard verify runtime` → Intent: verify → Technology Plan generated → Investigation Graph grows → Knowledge Graph fills → Report produced

`wizard investigate architecture` → Same path. Different goals. Same graphs.

This design means adding a new command is trivial — define a new intent type. Adding support for a new technology requires no code at all — the Planner's LLM already knows it.

---

## The Full Investigation Flow

```
User runs command
      ↓
CLI parses command → creates Investigation Request
      ↓
Runtime Engine: Investigation Manager creates Investigation
Both graphs initialized (empty)
      ↓
Repository Manager: Fast Scanner reads repo metadata
→ produces Repository Manifest
      ↓
Investigation Planner: initial LLM call with manifest
→ produces Technology Plan (technologies + goals + priority files)
      ↓
Runtime Engine: Goal set created, root Investigation Nodes added to Investigation Graph
      ↓
Investigation Loop:
  Priority Engine selects next Investigation Node
  ↓
  Runtime executes node (Sandbox + Tool Runtime)
  ↓
  Observation created (immutable, points to Investigation Node)
  ↓
  Hypothesis evaluated:
    Expected? → Claim created deterministically (no LLM)
    Unexpected? → Planner consulted → new Nodes created
  ↓
  Extractor Framework → Claim validated
  ↓
  Evidence Engine → Observation linked to Claim
  ↓
  Knowledge Graph updated
  ↓
  Trust Engine recalculates
  ↓
  Goal Engine evaluates Checkpoint Nodes
  ↓
  Planner creates next Investigation Nodes
  ↓
  Back to top of loop
      ↓
Convergence:
  All Checkpoint Nodes satisfied
  ↓
Report Generator reads both graphs + Observation Store
→ produces verification_report.md
      ↓
CLI displays results to user
```

---

## What Each Contributor Owns

### Koshal — Command Line Interface

Everything between the user and the Runtime Engine.

Responsibilities:
- The four commands: investigate, verify, report, explain
- Parsing and validating commands
- Assembling Investigation Requests
- Calling the Runtime Engine API
- Displaying progress and results

The CLI never analyzes, never calls the Planner or agents directly, never modifies either graph.

**Tech stack: Undefined.** Koshal should propose one (Python + Typer/Click is a natural fit).

---

### Shivam — Runtime Engine

The complete investigation engine and both graphs.

Responsibilities:
- Runtime Kernel
- Investigation Manager
- Repository Manager + Fast Scanner
- Sandbox Manager + Tool Runtime
- Observation Engine
- Event Bus
- Investigation Graph (new critical subsystem)
- Extractor Framework
- Evidence Engine
- Knowledge Graph
- Trust Engine
- Goal Engine
- Priority Engine
- Report Generator
- The APIs that CLI, Planner, and Agents use to communicate with the Runtime

Critical: Design the Investigation Graph early. It is the backbone of the architecture. Everything else depends on it.

**Tech stack: Undefined.** Shivam should propose one.

---

### Diksha — Agent System

The two AI agents and their n8n workflows.

Responsibilities:
- Explorer Agent n8n workflow
- Verification Agent n8n workflow
- System prompts for both agents
- Coordinating with Shivam on the agent API
- Defining when agents are invoked vs. when the Planner handles it alone

Key distinction: The agents handle complex reasoning that the Planner's structured node approach cannot cover. The Planner handles the majority of the investigation. The agents handle edge cases and deep reasoning.

**Tech stack: n8n for orchestration. LLM provider: Undefined.**

---

### Yash — Investigation Planner

The dynamic investigation planning system.

Responsibilities:
- Fast Scanner implementation
- Repository Manifest format design
- Technology Plan format design
- Initial planning prompt (the prompt sent to the LLM with the Repository Manifest)
- Investigation Node format design (all node types, the hypothesis field structure, success/failure claim templates)
- Ongoing planning prompts (used when the Planner is called during the investigation loop)
- Escalation condition definitions (what triggers a Planner consultation vs. deterministic evaluation)
- Coordinating with Shivam on how the Planner integrates with the Investigation Graph

**Tech stack: Undefined.** The Planner is primarily a prompt engineering and data format problem. LLM provider also undefined.

---

## Rules Every Contributor Must Follow

### The Runtime Engine owns truth

No other subsystem may decide whether a Claim is verified. The Planner may plan. The agents may reason. But only the Runtime Engine verifies.

### The Planner and agents never modify the graphs directly

Claims enter the Knowledge Graph only through the Evidence Engine. Investigation Nodes are added to the Investigation Graph only when the Runtime Engine creates them from Planner-returned node definitions.

### Observations are immutable

Once created, observations cannot be changed. New information creates new observations.

### The Planner never receives the entire repository

The Repository Manifest is the maximum initial context. Additional file contents are provided only on demand, one file at a time.

### Hypotheses enable deterministic evaluation

Every Investigation Node should carry a hypothesis that allows the Runtime Engine to evaluate expected outcomes without calling the LLM. Only truly unexpected outcomes should escalate.

### Reports are evidence-backed

Every statement in the Verification Report must trace back to Claims. Every Claim must trace back to Investigation Nodes. Every node must trace back to Observations.

### Every repository is untrusted

All repository code executes inside a Sandbox. No exceptions.

### Every investigation is independent

Investigations never share state. Each produces its own graphs, observations, and report.

---

## Glossary Quick Reference

| Term | One-Line Definition |
|---|---|
| Investigation | One complete verification session |
| Repository Manifest | Fast scan output: file tree + metadata, no contents |
| Technology Plan | Initial Planner output: technologies + goals + priority files |
| Investigation Graph | The graph of how investigation is proceeding (Investigation Nodes) |
| Knowledge Graph | The graph of what has been learned (Claims) |
| Investigation Node | A unit of work in the Investigation Graph |
| Hypothesis | What the Planner expects a node to find |
| Observation | Immutable raw fact from a tool execution |
| Claim | Validated structured knowledge in the Knowledge Graph |
| Evidence | The link between Observations and Claims |
| Trust | Runtime-computed confidence in a Claim |
| Goal | A verification objective (Checkpoint Node in the Investigation Graph) |
| Escalation | Planner consultation when a node produces an unexpected result |
| Progressive Context | Strategy of sending only metadata first, then targeted files on demand |
| Sandbox | Isolated execution environment for all repository interactions |
| Convergence | When all Checkpoint Nodes are satisfied and investigation ends |
