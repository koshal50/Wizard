# Wizard

**Evidence Driven Runtime for Autonomous Software Repository Verification**

Wizard is a software tool that autonomously investigates unknown software repositories, gathers evidence about how they work, verifies that evidence, and produces a clear, structured verification report. It does not guess. It does not trust documentation blindly. It investigates, collects evidence, and only then produces conclusions.

---

## What Wizard Does

When you point Wizard at a repository, it does the following things in order.

1. It scans the repository to understand what technologies are present.
2. It creates a set of verification goals based on what it discovers.
3. It sends an AI agent to explore the repository and gather information.
4. It converts every piece of information into structured, immutable observations.
5. It builds a knowledge graph from those observations.
6. It calculates how much to trust each piece of knowledge.
7. It updates its goals as new information arrives.
8. It continues this loop until it has enough evidence.
9. It generates a verification report explaining everything it found.

Every conclusion in the final report is backed by traceable evidence. Nothing appears as unexplained "AI magic."

---

## The Problem Wizard Solves

AI coding assistants can generate thousands of lines of code in minutes. The resulting repositories are often:

- Missing dependencies
- Lacking execution instructions
- Containing hallucinated references to files or APIs that do not exist
- Inconsistent between documentation and actual code
- Unknown in terms of how they should actually run

Traditional tools do not help here. Static analyzers read code but do not execute it. Testing frameworks assume the project already works. Wizard fills the gap by autonomously investigating what a repository actually does, not just what it claims to do.

---

## Core Design Principle

Wizard separates intelligence from verification.

The AI agent is responsible for exploring the repository and forming hypotheses. The Runtime Engine is responsible for deciding what is actually true. The agent can explore freely. The runtime verifies every conclusion before accepting it.

This means the system cannot hallucinate its way into a false verification report. Every statement in the output must be supported by real evidence collected during the investigation.

---

## Command Line Interface

Wizard is used through a command line interface. The four primary command families are:

```bash
wizard investigate <target>
wizard verify <target>
wizard report
wizard explain <target>
```

Details on every command and how they work internally are covered in the documentation.

---

## The Four Subsystems

Wizard is built from four independent subsystems. Each subsystem is owned by one team member.

| Subsystem | Responsibility |
|---|---|
| CLI | Accepts user commands and translates them into investigation requests |
| Runtime Engine | Manages the complete investigation lifecycle and owns all verification logic |
| Knowledge System | Teaches the runtime how to understand different technologies |
| Agent System | Explores the repository and supplies the runtime with observations |

---

## Documentation

The complete architecture documentation lives in `docs/main/`. Read the documents in the order listed below to build a full understanding of the system.

| Document | What It Covers |
|---|---|
| [wizard.md](docs/main/wizard.md) | Complete contributor guide covering every system in depth |
| [overview.md](docs/main/overview.md) | High level architecture and how all four subsystems connect |
| [investigation-lifecycle.md](docs/main/investigation-lifecycle.md) | How a single investigation progresses from start to finish |
| [runtime-engine.md](docs/main/runtime-engine.md) | The Runtime Engine and all its internal subsystems |
| [knowledge-system.md](docs/main/knowledge-system.md) | Knowledge Modules, the Knowledge Registry, and how technologies are supported |
| [agent-system.md](docs/main/agent-system.md) | The AI agent, its workflow in n8n, and how it communicates with the runtime |
| [cli.md](docs/main/cli.md) | The command line interface, all four commands, and how they map to investigations |
| [core-concepts.md](docs/main/core-concepts.md) | Definitions of every important term used throughout the project |
| [verification-report.md](docs/main/verification-report.md) | The structure and content of the final verification report |

---

## Project Status

This project is under active development by a team of four contributors. The architecture is defined. Implementation is in progress.

- Tech stack for the CLI and Runtime Engine: **undefined**
- Tech stack for the Knowledge System: **undefined**
- Tech stack for the Agent System: **n8n** (decided)

---

## Contributors

See `docs/members/` for individual contributor documentation.

- Koshal — Command Line Interface and Investigation Entry
- Shivam — Wizard Runtime Engine
- Diksha — Agent System
- Yash — Knowledge System
