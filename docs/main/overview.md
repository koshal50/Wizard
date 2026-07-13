# System Overview

This document describes the high level architecture of Wizard and explains how the four major subsystems connect to each other.

---

## What Wizard Is

Wizard is an autonomous software repository verification system. It investigates unknown software repositories, collects evidence about how they work, verifies that evidence through actual execution, and produces a structured verification report.

Wizard separates intelligence from verification. An AI agent explores and reasons. A planning component generates investigation steps. The Runtime Engine independently verifies every conclusion before accepting it as true.

The system can investigate repositories using any technology — including technologies that did not exist when Wizard was built — because technology understanding comes from an LLM planner, not from hardcoded modules.

---

## The Four Subsystems

Wizard is composed of four subsystems. Each subsystem has a single, well-defined responsibility.

```
┌─────────────────────────────────────────────────────────────────────┐
│                         User                                        │
└─────────────────────────────────┬───────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Command Line Interface                           │
│                                                                     │
│  Accepts commands. Creates Investigation Requests.                  │
│  Displays progress and results.                                     │
└─────────────────────────────────┬───────────────────────────────────┘
                                  │  Investigation Request
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Runtime Engine                                 │
│                                                                     │
│  Manages the complete investigation lifecycle.                      │
│  Owns all verification logic. Owns both graphs.                     │
│  Computes trust. Evaluates goals. Generates reports.                │
│                                                                     │
│    ┌───────────────────┬────────────────┬──────────────────┐        │
│    │ Investigation     │  Knowledge     │    Sandbox       │        │
│    │ Planner           │  Graph         │                  │        │
│    └───────────────────┴────────────────┴──────────────────┘        │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
                       verification_report.md
```

### Command Line Interface

The CLI is the entry point. It receives commands from the user, parses them, and converts them into Investigation Requests that the Runtime Engine understands. It then monitors progress and displays results.

The CLI does not perform any analysis. It only translates user commands into structured requests.

### Runtime Engine

The Runtime Engine is the core of Wizard. It owns everything.

It creates and manages investigations. It executes the fast repository scan. It calls the Investigation Planner to generate the investigation plan. It builds and maintains both graphs throughout the investigation. It executes tools in the sandbox. It stores observations. It runs extractors. It computes trust. It evaluates goals. It generates the report.

Everything passes through the Runtime Engine.

### Investigation Planner

The Investigation Planner replaces the static Knowledge Module system.

Instead of hardcoded plugins that only understand technologies their authors programmed, the Planner uses an LLM to dynamically generate investigation plans for any repository, any technology, any era.

The Planner operates in two modes:

**Initial planning:** After the fast repository scan produces the Repository Manifest, the Planner calls the LLM to generate a Technology Plan — what technologies appear to be present, what goals should be created, which files should be read first.

**Ongoing node creation:** Throughout the investigation loop, the Planner is called to create Investigation Nodes — specific units of work with typed actions, hypotheses about expected outcomes, and claims to create based on the result.

The Planner never sends the entire repository to the LLM. It works with the compact Repository Manifest and progressively reads only the files that are needed.

### Agent System

The Agent System provides deeper reasoning for complex, ambiguous situations.

The two agents — Explorer and Verifier — are built in n8n. They handle scenarios where the Planner's structured node-based approach is insufficient: understanding the overall design intent of a codebase, interpreting ambiguous execution outputs, suggesting investigation directions when contradictions cannot be resolved through simple pattern matching.

The agents communicate with the Runtime Engine through a stable API. They return structured requests. They never modify the graphs directly.

---

## The Two Graphs

The most distinctive architectural feature of Wizard is that it maintains two separate graphs throughout every investigation.

### Knowledge Graph

The Knowledge Graph stores what the Runtime has learned about the repository.

Every node is a Claim — a fact about the repository. Every edge is a relationship between claims (DEPENDS_ON, USES, CONTRADICTS, etc.).

This graph answers the question: **what do we know?**

It starts empty and grows as evidence accumulates. Claims enter only after passing through the Evidence Engine and Trust Engine. The Planner and agents cannot insert claims directly.

### Investigation Graph

The Investigation Graph stores how the investigation is proceeding.

Every node is an Investigation Node — a unit of work (read this file, run this command, verify this claim). Edges represent dependencies between nodes (this node must complete before that one can run).

This graph answers the question: **how are we getting there?**

It starts with the root goal and grows dynamically as the Planner creates new nodes. Each node carries a hypothesis about what it expects to find. The Runtime evaluates expected outcomes deterministically without consulting the LLM. Only unexpected outcomes trigger a Planner consultation.

The two graphs reference each other. Investigation Nodes produce Claims that enter the Knowledge Graph. Knowledge Graph state informs what the Planner puts into the next Investigation Node.

---

## How Information Flows

Every piece of information follows the same path.

```
Repository Fast Scan
      ↓
Repository Manifest (file tree + metadata, no contents)
      ↓
Investigation Planner: Initial Technology Plan
      ↓
Runtime creates Goals + root Investigation Graph nodes
      ↓
Investigation Node executes (read file / run command)
      ↓
Observation created (immutable)
      ↓
Hypothesis evaluated deterministically
      ↓
Claim created and enters Knowledge Graph
      ↓
Evidence links Observation to Claim
      ↓
Trust Engine recalculates
      ↓
Planner creates next Investigation Node
      ↓
Loop continues until Goal Checkpoint satisfied
      ↓
Report Generator assembles verification_report.md
```

---

## Why There Is Only One Runtime Architecture

Every command — `investigate`, `verify`, `explain`, `report` — uses the same Runtime Engine and the same two-graph architecture. The only difference is the intent and the goals that get created.

Adding a new command requires only defining a new intent type. Adding support for a new technology requires no code at all — the Planner's LLM already understands it.

---

## What Each Contributor Is Responsible For

| Contributor | Subsystem | Primary Output |
|---|---|---|
| Koshal | Command Line Interface | Working CLI with 4 commands |
| Shivam | Runtime Engine | Complete investigation engine with both graphs, all subsystems |
| Diksha | Agent System | Two n8n workflows (Explorer and Verification agents) |
| Yash | Investigation Planner | Fast Scanner, Repository Manifest, Technology Plan, Investigation Node formats and prompts |

The contracts between subsystems — the Investigation Request format, the Investigation Node format, the Repository Manifest format, the Agent API — must be agreed upon by all contributors before implementation begins.
