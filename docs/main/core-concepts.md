# Core Concepts

This document defines every important concept in Wizard. All contributors must use these terms consistently.

---

## Investigation

One complete repository verification session.

Every user command creates a new Investigation. It is the root object that owns everything — both graphs, all observations, all goals, the report.

Investigations are isolated. Two investigations of the same repository never share runtime state.

**Do not call it:** run, execution, analysis, scan, session

---

## Investigation Request

The structured object the CLI sends to the Runtime Engine to start a new investigation.

Contains: repository location, intent, targets, options.

---

## Repository Manifest

The output of the Fast Scanner. A compact, structured summary of the repository's surface — file names, directory tree, extensions, sizes, and presence of well-known signal files.

No file contents. Typically 200 to 500 tokens.

This is what the Investigation Planner receives for its initial planning call.

---

## Technology Plan

The structured JSON document the Investigation Planner produces after its initial LLM call.

Lists the technologies that appear to be present, with what goals to create for each and what files to read first.

The Runtime Engine uses the Technology Plan to generate the initial Goal set and the root nodes of the Investigation Graph.

---

## Investigation Graph

The directed graph that records how the investigation is proceeding.

Every node is an Investigation Node — a unit of work. Every edge represents a dependency between nodes (this node must complete before that one can run).

The Investigation Graph starts with the root goal and grows dynamically as the Planner creates new nodes. It answers the question: **how are we getting there?**

The complete Investigation Graph is stored permanently after the investigation ends. Every Claim in the Knowledge Graph can be traced back to the Investigation Graph node that produced it.

---

## Knowledge Graph

The directed graph that records what the Runtime Engine has learned about the repository.

Every node is a Claim. Every edge is a typed relationship between Claims (DEPENDS_ON, USES, CONTRADICTS, PROVIDES, etc.).

The Knowledge Graph answers the question: **what do we know?**

The Knowledge Graph starts empty and grows as evidence is validated. Claims enter only through the Evidence Engine. The Planner and agents cannot insert Claims directly.

---

## Investigation Node

A single unit of work in the Investigation Graph.

Every Investigation Node carries:
- **A type** (Discovery, Read, Execute, Parse, Verify, Synthesize, Planner, Checkpoint)
- **An action** (what the Runtime Engine should do)
- **A hypothesis** (what the Planner expects to find)
- **A success claim template** (what Claim to create if hypothesis confirmed)
- **A failure claim template** (what Claim to create if hypothesis refuted)
- **Dependencies** (which other nodes must complete first)

Investigation Nodes are created by the Investigation Planner. They are executed by the Runtime Engine.

---

## Hypothesis

The Planner's declaration of what an Investigation Node is expected to find.

The Runtime Engine evaluates the node's actual output against the hypothesis deterministically. If the result matches an expected outcome (success or failure), the appropriate Claim is created without consulting the LLM. Only unexpected results trigger a Planner consultation.

The Hypothesis field is what makes the investigation loop efficient. Most node evaluations complete without any LLM call.

---

## Investigation Planner

The component that generates investigation plans using an LLM.

In the initial phase: receives the Repository Manifest, calls the LLM, returns the Technology Plan and initial Investigation Graph nodes.

During the investigation loop: receives a compact summary of current investigation state, calls the LLM, returns the next Investigation Node(s) to create.

The Planner never sends the entire repository to the LLM. It sends only the Repository Manifest and the specific file contents that have been read so far.

The Planner is not a verifier. It is a planner. It cannot insert Claims into the Knowledge Graph or mark goals complete.

---

## Intent

What the user wants to achieve. Created by the CLI from the user's command.

Intents become Goals. The Runtime Engine converts Intent into initial Goals via the Technology Plan.

---

## Goal

An internal Runtime Engine objective representing something that needs to be verified.

Goals are represented as Checkpoint Nodes in the Investigation Graph. A Checkpoint Node is satisfied when all required Claims are present with sufficient trust.

Goals can be created dynamically mid-investigation if the Planner determines something new needs to be verified.

**Do not call it:** task, step, objective, checkpoint (as a standalone term)

---

## Observation

An immutable fact collected during the investigation.

Created when an Investigation Node executes. Contains the raw output from a tool call — file contents, command output, exit code, etc.

Observations are immutable. Once created, they cannot be changed. Every Observation carries the ID of the Investigation Node that produced it, making every Claim fully traceable.

**Do not call it:** finding, result, insight, evidence, log

---

## Claim

A structured piece of repository knowledge derived from Observations.

Claims are validated facts about the repository: "Runtime = Node.js 18", "Framework = Express 4.18", "Container = Docker".

Claims enter the Knowledge Graph only after passing the Evidence Engine. Every Claim carries:
- A type
- A value
- Its supporting Evidence
- Its contradictory Evidence (if any)
- A trust level
- The Investigation Node ID that created it

Claims evolve throughout the investigation as new evidence arrives.

**Do not call it:** belief, fact, knowledge, result

---

## Evidence

What connects Observations to Claims.

Evidence answers: "Why does the Runtime Engine believe this Claim?"

Every Claim must have at least one piece of Evidence. Evidence is supporting (confirms the Claim) or contradictory (challenges it).

The Evidence Engine prevents the same Observation from being counted multiple times.

---

## Trust

The Runtime Engine's computed confidence in a Claim.

Not assigned by the Planner. Not assigned by the agent. Calculated by the Trust Engine using real evidence.

Considers: number of independent supporting Observations, source reliability (execution > config > docs), contradictions, and graph relationships to other trusted Claims.

Trust propagates through the Knowledge Graph — updating one Claim's trust can affect dependent Claims.

---

## Extractor

A component that converts an Observation into one or more Claims.

**Deterministic Extractors** parse structured data. No LLM. Always produce the same output for the same input.

**Cognitive Extractors** use an LLM for ambiguous data. The resulting Claims still pass Runtime validation.

---

## Sandbox

An isolated execution environment. Every repository interaction runs inside a Sandbox. Repositories are always untrusted.

After execution, the Sandbox is destroyed. The Sandbox enforces resource limits and captures all outputs.

---

## Tool

A controlled operation the Runtime Engine can execute inside the Sandbox.

Examples: Read File, Execute Command, Search Repository, Check Network Port.

Tools never modify the graphs. They collect information, which becomes Observations.

---

## Verification Report

The final document produced after an investigation converges.

Every statement references Claims from the Knowledge Graph. Every Claim references the Investigation Graph node that produced it. Every node references the Observations that triggered it.

Nothing in the report is invented. The full audit trail connects every conclusion back to raw evidence.

---

## Fast Scanner

The component of the Repository Manager that produces the Repository Manifest.

Reads only metadata (file names, extensions, sizes). Does not read file contents. Designed to be extremely fast even on large repositories.

---

## Repository Manifest

The output of the Fast Scanner. Described above under Repository Manifest.

---

## Progressive Context

The strategy of never sending the entire repository to the LLM.

The Planner's initial call receives only the Repository Manifest. Subsequent calls receive only the file contents that have been read so far, plus a compact summary of recent Investigation Graph activity.

File contents are read on demand, one file at a time, when an Investigation Node requires them.

---

## Convergence

The investigation state when the Runtime Engine determines that sufficient evidence has been collected.

The investigation converges when:
- All active Checkpoint Nodes are satisfied
- No significant unresolved contradictions remain
- The Priority Engine determines additional investigation would provide little new value

---

## Escalation

What happens when an Investigation Node produces an unexpected result.

When the node's actual output does not match the expected hypothesis pattern, the Runtime Engine escalates to the Investigation Planner. The Planner is given the unexpected result and decides how to interpret it and what Investigation Node to create next.

Escalation is the mechanism that handles edge cases and unusual repository configurations without requiring the Planner to predict them in advance.

---

## Runtime Kernel

The central coordinator of the Runtime Engine. Manages all subsystems, lifecycle transitions, and event dispatching. Does not perform analysis itself.

---

## Event Bus

The communication mechanism between Runtime subsystems. Subsystems publish events. Others subscribe. Prevents tight coupling.

---

## Budget

The maximum number of Investigation Node executions allowed in a single investigation.

Prevents investigations from running indefinitely. When exhausted, the Runtime stops gracefully and produces the best report from collected evidence.
