# Core Concepts

This document defines every important concept used throughout the Wizard project. All contributors should use these terms consistently. Using different names for the same concept creates confusion.

---

## Investigation

An Investigation is one complete repository verification session.

Every user command creates a new Investigation. The Investigation is the root object that owns everything that happens during repository analysis — observations, claims, evidence, goals, trust values, and the final report.

Investigations are independent from each other. Two investigations of the same repository never share state. Each investigation is a fresh, isolated snapshot of what was discovered during that specific run.

An Investigation has a unique ID, a lifecycle state, a budget, and references to all the data it has collected.

**Do not call it:** run, execution, analysis, scan, session

---

## Investigation Request

An Investigation Request is the structured object the CLI sends to the Runtime Engine to start a new investigation.

It contains the repository location, the user's intent, the investigation targets, and any options the user specified.

The Runtime Engine validates this object before creating an Investigation.

---

## Investigation Context

An Investigation Context is the snapshot of information the Runtime Engine sends to the Explorer Agent at the beginning of each reasoning iteration.

It contains:
- The active goals
- The current Claim Graph state
- Missing evidence
- Previously failed actions
- Available tools
- Remaining budget
- Repository metadata

The agent uses this to decide what to investigate next. The agent never receives the internal implementation of the Runtime Engine — only this context object.

---

## Intent

An Intent describes what the user wants to achieve.

Intents do not describe how the investigation should be performed. They define the desired outcome.

Examples:
- Intent: Verify Runtime (the user wants to know if the runtime works)
- Intent: Investigate Architecture (the user wants to understand the codebase structure)
- Intent: Explain Dependencies (the user wants an explanation of what the project needs)

The CLI creates Intents from user commands. The Runtime Engine converts Intents into Goals.

---

## Goal

A Goal is an internal Runtime Engine object representing a specific verification objective.

Goals are not the same as user commands. When a user says "verify runtime," that becomes an Intent. The Runtime Engine converts that Intent into one or more Goals like "Verify Node.js Runtime," "Verify Docker Container," and "Verify Application Startup."

Goals have states:

| State | Meaning |
|---|---|
| Waiting | Not started yet |
| Investigating | Evidence is being gathered |
| Partially Verified | Some evidence exists but more is needed |
| Verified | Sufficient evidence has been collected |
| Blocked | Cannot proceed because a prerequisite goal is unresolved |
| Failed | Cannot be satisfied with available resources |
| Completed | Investigation finished (either verified or definitively failed) |

Goals can be created dynamically during an investigation. If the Runtime Engine discovers a technology it did not know about at the start, it creates new goals for that technology automatically.

**Do not call it:** task, step, objective, checkpoint

---

## Observation

An Observation is an immutable fact collected during the investigation.

Observations are the most basic unit of information in Wizard. They contain raw data — they do not interpret or explain anything. They simply record what happened.

Examples:
- The content of the file `package.json`
- The standard output of running `npm install`
- The exit code of running `python app.py`
- A "file not found" error when looking for `.env`
- The response headers from a request to `localhost:3000`

Observations are immutable. Once created, they cannot be changed. If new information is collected, a new Observation is created. This guarantees complete traceability — you can always see exactly what raw data the system was working with.

Every Observation has:
- A unique Observation ID
- A timestamp
- The source (which tool produced it)
- The observation type (file content, command output, error, etc.)
- The raw payload
- The repository path it relates to (if applicable)
- The Investigation ID

**Do not call it:** finding, result, insight, evidence, log

---

## Claim

A Claim is a structured piece of repository knowledge derived from observations.

Claims are what the Runtime Engine believes about the repository. Unlike Observations (which are raw facts), Claims are interpretations.

Examples:
- "Runtime = Node.js 18"
- "Framework = Express 4.18"
- "Database = PostgreSQL"
- "Deployment = Docker Compose"
- "Entry Point = server.js"

Claims evolve throughout the investigation. Additional evidence may increase trust in a claim. Contradictory evidence may decrease trust. New observations may completely invalidate a previous claim.

Every Claim:
- Has a unique ID
- Has a type (Runtime, Framework, Dependency, Deployment, etc.)
- Has a value
- References its supporting evidence
- References any contradictory evidence
- Has a trust level

**Do not call it:** belief, fact, knowledge, result

---

## Evidence

Evidence is what connects Observations to Claims.

Evidence answers the question: "Why does the Runtime Engine believe this claim?"

Every Claim must have at least one piece of Evidence. Claims without evidence are hypotheses — the Runtime Engine does not accept them into the Claim Graph as verified knowledge.

Evidence is created by the Evidence Engine. It links one or more Observations to one Claim, along with information about the source's reliability.

Evidence can be supporting (it supports the claim) or contradictory (it challenges the claim).

**Do not call it:** observation, fact, proof, data

---

## Trust

Trust represents how strongly the Runtime Engine believes a Claim based on all available Evidence.

Trust is not a number assigned by the AI agent. It is calculated by the Trust Engine using real, collected evidence. The agent cannot set trust values.

Trust considers:
- The number of supporting observations
- The independence of those observations (observations from different sources count more than multiple observations from the same source)
- The reliability of each source (execution results > configuration files > documentation)
- The presence of contradictory evidence
- Relationships to other trusted claims

Trust is not static. It changes throughout the investigation as new evidence arrives.

---

## Claim Graph

The Claim Graph is the Runtime Engine's internal knowledge model of the repository.

Every node in the graph is a Claim. Every edge is a relationship between Claims.

The Claim Graph starts empty at the beginning of every investigation and grows as claims are added. Every repository produces its own unique Claim Graph.

Relationships between claims:

| Relationship | Meaning |
|---|---|
| DEPENDS_ON | One technology depends on another |
| REQUIRES | Something requires something else to function |
| USES | One component uses another |
| IMPLEMENTS | Something implements an interface or pattern |
| CONTAINS | A container contains components |
| PROVIDES | Something provides a service or capability |
| CONTRADICTS | Two claims are mutually inconsistent |
| MUTUALLY_EXCLUSIVE | Only one of several claims can be true |

The Claim Graph is important because repository knowledge is relational. A framework depends on a runtime. A deployment depends on containers. Storing claims as isolated facts would lose this relational structure.

---

## Knowledge Module

A Knowledge Module is a self-contained package of knowledge about one technology or technology family.

Examples: Python module, Docker module, Node.js module, GitHub Actions module

Each module provides:
- Identification rules (how to tell if this technology is present)
- Claim types (what kinds of claims the module creates)
- Goal templates (what goals to generate when this technology is found)
- Extractors (how to convert observations into claims)
- Relationship templates (how claims from this module relate to other claims)
- Verification rules (what evidence is needed to satisfy goals from this module)
- Report contributions (optional sections to add to the verification report)

The Runtime Engine never contains technology-specific knowledge. All technology knowledge lives in Knowledge Modules.

---

## Knowledge Registry

The Knowledge Registry is the catalog that manages all available Knowledge Modules.

When Wizard starts, every module registers with the Registry. During Knowledge Discovery, the Runtime Engine queries the Registry to find which modules are relevant for the current repository. The Registry activates matching modules.

The Registry never performs repository analysis. It only manages the catalog of modules.

---

## Extractor

An Extractor converts a raw Observation into one or more structured Claims.

There are two kinds of extractors:

**Deterministic Extractors** parse structured data using rules, parsers, or regular expressions. They do not use AI. They always produce the same output for the same input. Use these whenever possible.

**Cognitive Extractors** use an LLM to extract meaning from unstructured data. The resulting claims must still pass Runtime validation.

Extractors are provided by Knowledge Modules. Each module includes the extractors needed to understand its technology.

---

## Sandbox

A Sandbox is an isolated execution environment.

Every time repository code is executed, it runs inside a Sandbox. The Sandbox prevents the repository from affecting the host system. After execution, the Sandbox is destroyed.

Repositories are always treated as untrusted. Even legitimate repositories may contain post-install scripts or startup commands with unexpected side effects. The Sandbox ensures that anything the repository does stays contained.

The Sandbox enforces resource limits (CPU, memory, disk, network) and captures all outputs.

---

## Tool

A Tool is a controlled operation that the agent can request.

Examples: Read File, Execute Command, Search Repository, Check Network Port

Every Tool:
- Has a name
- Has a defined input schema
- Has a defined output schema
- Declares what permissions it needs
- Declares what sandbox capabilities it requires

Tools never modify the Claim Graph. They only collect information. The Runtime Engine converts tool outputs into Observations.

---

## Tool Request

A Tool Request is the structured object the agent returns to the Runtime Engine.

It specifies which tool to run, with what parameters, and optionally includes the agent's reasoning for why this tool was chosen.

The Runtime Engine validates every Tool Request before executing it.

---

## Tool Response

A Tool Response is the standardized result of executing a tool.

It contains:
- Success or failure status
- Exit code
- Standard output
- Standard error
- Generated files
- Execution duration
- Resource usage

The Observation Engine converts Tool Responses into Observations.

---

## Verification Report

The Verification Report is the final document produced by Wizard after an investigation completes.

It summarizes everything the Runtime Engine discovered, explains why it reached each conclusion, identifies what evidence supports each finding, and documents what remains uncertain.

The report is saved as `verification_report.md`. Every statement in the report is backed by evidence — nothing appears without justification.

The complete structure of the Verification Report is described in `verification-report.md`.

---

## Runtime Kernel

The Runtime Kernel is the central coordinator of the Runtime Engine.

It manages all Runtime subsystems, coordinates investigation lifecycle transitions, dispatches events, and manages subsystem registration. It does not perform analysis itself — it coordinates the subsystems that do.

---

## Event Bus

The Event Bus is the communication mechanism between Runtime subsystems.

Subsystems publish events when something important happens. Other subsystems subscribe to the events they care about. This decouples subsystems from each other and makes it easy to add new components.

---

## Convergence

Convergence is the state when an investigation has collected sufficient evidence and is ready to generate the final report.

Convergence happens when:
- All primary goals have been verified with sufficient evidence
- No significant unresolved contradictions remain
- Additional investigation is unlikely to produce meaningful new information

The Runtime Engine determines when convergence is reached. The agent cannot force or prevent convergence.

---

## Budget

An investigation Budget is the maximum number of tool executions allowed in a single investigation.

Budgets exist to prevent investigations from running indefinitely on large or complex repositories. When the budget is exhausted, the investigation ends gracefully and produces the best report possible from whatever evidence has been collected.
