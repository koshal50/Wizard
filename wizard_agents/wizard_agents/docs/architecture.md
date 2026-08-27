# Architecture

## Position in Wizard

This repository (`wizard_agents`) implements only the **Agent System**
subsystem of the larger Wizard architecture:

```
Investigation Planner
      |
      v
Investigation Nodes + Route
      |
      v
 Explorer Agent            <-- this subsystem
      |
      v
Tool Request / Execution Plan
      |
      v
 Runtime Engine             <-- separate subsystem (not implemented here)
      |
      v
Repository / Tools
      |
      v
Observations
      |
      v
Claims Graph
      |
      v
 Verification Agent         <-- this subsystem
      |
      v
Verification Assessment
      |
      v
Runtime / Report Generator  <-- separate subsystem (not implemented here)
      |
      v
verification_report.md
```

## Core principle

**Agents reason. Runtime executes.**

Explorer and Verification never touch the repository, sandbox, filesystem,
Claims Graph, trust scores, or goal-completion state. They consume
structured input and produce structured, validated output. Every side
effect (running a command, reading a file, writing the final report,
updating trust) belongs to the Runtime Engine, which is a separate
subsystem built independently.

## Components

| Component | Responsibility |
|---|---|
| `app/contracts` | Pydantic schemas defining the exact input/output shape of both agents. This is the integration surface other subsystems build against. |
| `app/llm` | `LLMProvider` abstraction plus `MockLLMProvider` (offline, deterministic) and `VLLMProvider` (real, open-source model via vLLM). |
| `app/prompts` | System/user prompt templates for each agent. |
| `app/validation` | Semantic validation of LLM output beyond Pydantic parsing (unknown tools, hallucinated claims, budget violations, etc). |
| `app/explorer` | `ExplorerAgent` — turns an `ExplorerInput` into a validated `ExplorerOutput`. |
| `app/verification` | `VerificationAgent` — turns a `VerificationInput` into a validated `VerificationOutput`. |
| `app/api` | FastAPI app exposing both agents over REST/JSON. |
| `app/adapters` | The `RuntimeExecutor` interface Runtime is expected to satisfy, plus a `MockRuntimeExecutor` used only by this subsystem's own tests/examples. |

## Why this stack

The brief calls for the simplest reliable stack: Python, FastAPI,
Pydantic, pytest, REST/JSON, Markdown, and a small LLM provider
abstraction. No vector database, no LangChain, no orchestration
framework is required — the agents are stateless request/response
transformations, so a general-purpose Python web framework and a
schema-validation library are sufficient and keep the codebase easy for
other developers to read and integrate against.

## Data flow within this subsystem

1. Runtime/Planner constructs an `ExplorerInput` (node, route, context,
   available tools, budget) and calls `POST /explorer/investigate`.
2. `ExplorerAgent` builds a prompt, calls the configured `LLMProvider`,
   and validates the result twice: once via Pydantic (shape), once via
   `validate_explorer_output` (semantic consistency with the input —
   known node ids, allow-listed tools, budget limits).
3. Runtime executes the resulting `ToolRequest` itself and produces an
   `Observation` (an entirely Runtime-owned type).
4. Runtime updates its Claims Graph and constructs a `VerificationInput`
   from the resulting claims/evidence, then calls `POST
   /verification/verify`.
5. `VerificationAgent` builds a prompt, calls the LLM provider, and
   validates the result (shape + no hallucinated claim ids + no
   contradictory finding states).
6. Runtime takes `VerificationOutput.report_markdown` (plus the
   structured fields) and writes the authoritative `verification_report.md`.
