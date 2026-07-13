# Runtime Engine

This document describes the Wizard Runtime Engine — what it is, what each of its internal subsystems does, and how they all work together.

---

## What the Runtime Engine Is

The Runtime Engine is the core of Wizard. Every important operation in the system passes through it. It is responsible for the complete investigation lifecycle, all verification logic, all state management, and the final report.

The Runtime Engine is intentionally deterministic. This means that given the same repository and the same observations, it will always produce the same conclusions. This makes investigations reproducible, explainable, and testable independently from the AI agent.

Think of it like an operating system kernel. The kernel does not do all the work itself. It coordinates the subsystems that do the work. The Runtime Engine is Wizard's kernel.

---

## What the Runtime Engine Is Not

Understanding what the Runtime Engine is not is just as important as understanding what it is.

The Runtime Engine is not intelligent. It does not reason. It does not form hypotheses. It does not decide what is interesting about a repository. That is the job of the AI agents.

The Runtime Engine does not know about specific technologies. It does not know what a `Dockerfile` means or what `requirements.txt` contains. That knowledge belongs in Knowledge Modules.

The Runtime Engine does not accept commands from users directly. That is the job of the CLI.

The Runtime Engine's job is verification, coordination, and state management. Nothing more.

---

## The 13 Subsystems

The Runtime Engine is composed of 13 subsystems. Each subsystem owns exactly one responsibility. They communicate through the Event Bus.

```
                    Runtime Kernel
                          │
   ┌──────────────────────┼──────────────────────┐
   │                      │                      │
   ▼                      ▼                      ▼
Investigation Manager   Event Bus          Knowledge Registry
   │
   ├── Repository Manager
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
   ├── Claim Graph
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

The Runtime Kernel is the central coordinator. It is the first thing that starts when Wizard runs and the last thing to shut down.

The Kernel manages:
- Bringing all other subsystems online during startup
- Creating and routing Investigation Requests
- Coordinating investigation lifecycle transitions
- Dispatching events between subsystems
- Managing subsystem registration
- Shutting down gracefully

The Kernel does not do analysis. It does not compute trust. It does not read files. It only manages coordination.

One useful mental model: the Runtime Kernel is to Wizard what an operating system kernel is to a computer. The kernel schedules work, manages resources, and makes sure subsystems can communicate. The actual work happens in the subsystems.

---

## Investigation Manager

The Investigation Manager owns every active Investigation.

When the Runtime Kernel receives an Investigation Request from the CLI, it hands the request to the Investigation Manager. The Investigation Manager creates the Investigation object, assigns it a unique ID, and initializes all its data stores.

Responsibilities:
- Creating new Investigations
- Loading repository metadata into the Investigation
- Tracking the current state of each Investigation
- Managing the investigation budget
- Coordinating the transition to each lifecycle stage
- Archiving completed Investigations

The Investigation Manager never reads files, never runs tools, and never analyzes anything. It manages the lifecycle.

---

## Repository Manager

The Repository Manager provides access to the repository being investigated.

When a new Investigation begins, the Repository Manager loads the repository. It creates a temporary working copy and provides the rest of the system with a controlled, safe way to access repository contents.

Responsibilities:
- Loading the repository from its source (local path, git URL, archive)
- Providing stable paths to repository files
- Maintaining metadata about the repository (total size, directory structure, file count)
- Creating temporary copies for safe execution
- Cleaning up temporary files when the investigation ends

The Repository Manager does not understand what files mean. It knows where files are and how to access them. Understanding what a file contains is the job of the Extractor Framework and Knowledge Modules.

---

## Sandbox Manager

The Sandbox Manager ensures that every repository interaction happens inside an isolated environment.

Every repository is treated as untrusted. A repository could contain malicious installation scripts, post-install hooks, or commands that would damage the host system. The Sandbox Manager prevents this by ensuring that repository code never executes directly on the host.

Responsibilities:
- Creating isolated execution environments before every tool execution
- Preparing the workspace inside the sandbox (copying files, setting environment variables)
- Enforcing resource limits (CPU, memory, disk, network)
- Capturing all outputs from sandbox execution
- Destroying the sandbox completely after execution ends

The exact sandbox technology is undefined — it could be Docker containers, lightweight VMs, or OS-level isolation. This decision belongs to the Runtime Engine contributor (Shivam).

---

## Tool Runtime

The Tool Runtime executes operations requested by the agent.

Tools are the only way the agent can interact with the repository. The agent cannot directly read files, run commands, or access the repository in any way. It can only submit Tool Requests. The Tool Runtime executes those requests inside the Sandbox.

Every tool follows the same interface:
- It accepts a set of parameters
- It executes one specific operation
- It returns a standardized response

Examples of built-in tools:

| Tool | What It Does |
|---|---|
| Read File | Reads the contents of a repository file |
| Read Directory | Lists the contents of a directory |
| Search Repository | Searches for files matching a pattern |
| Execute Command | Runs a shell command inside the sandbox |
| Read Configuration | Parses a configuration file |
| Inspect Environment | Lists available environment variables |
| Check Network Port | Tests whether a specific port is listening |

The Tool Runtime validates every Tool Request before execution. It checks that the tool is registered, the parameters are valid, the sandbox supports the requested operation, and the investigation budget allows it.

Failures during tool execution become observations. A `ModuleNotFoundError` when trying to install dependencies is not a system failure — it is a useful piece of evidence about the repository.

---

## Event Bus

The Event Bus is how subsystems communicate without depending on each other directly.

Instead of one subsystem calling another directly, subsystems publish events when something important happens. Other subsystems subscribe to the events they care about.

For example, when an Observation is created:
1. The Observation Engine publishes an "Observation Created" event
2. The Extractor Framework receives this event and begins extraction
3. A debugging component (if active) receives this event and logs it
4. A metrics component (if active) receives this event and updates counters

None of these components needed to know about each other. The Observation Engine just published the event. The others subscribed.

This design allows new components to be added without modifying existing code. A future analytics or visualization component can simply subscribe to existing events.

All events contain:
- An Event ID
- A timestamp
- The Investigation ID
- The event type
- The source subsystem
- A payload

Events are immutable and are retained as part of the investigation history.

---

## Observation Engine

The Observation Engine stores every observation generated during an investigation.

An observation is the most basic unit of information in Wizard. It is an immutable record of a single fact collected from the repository or from executing something against it.

Examples of observations:
- The contents of `package.json`
- The output of running `npm install`
- The exit code of running `python app.py`
- The response from making a request to `localhost:3000`
- A "file not found" error when looking for `.env`

Observations are immutable. Once created, they cannot be changed. If new information needs to be recorded, a new observation is created.

Every observation gets:
- A unique Observation ID
- A timestamp
- The source (which tool produced it)
- The observation type
- The raw payload (the actual data)
- The repository path it relates to (if applicable)
- The Investigation ID

The Observation Engine makes observations searchable and retrievable. Every conclusion in the final report can be traced back to specific observations.

---

## Extractor Framework

The Extractor Framework converts raw observations into structured claims.

An observation says "here is what happened." An extractor reads that observation and says "here is what it means."

For example:
- Observation: contents of `package.json` (raw JSON text)
- Extractor: identifies `"express": "^4.18.0"` in the dependencies section
- Claim produced: "Framework = Express, version ~4.18"

The Extractor Framework supports two types of extractors:

**Deterministic Extractors** parse structured data using rules, regular expressions, or parsers. They do not use AI. They are fast, reliable, and always produce the same output for the same input. Use these whenever possible.

**Cognitive Extractors** use an LLM to extract meaning from unstructured data. Use these only when the data cannot be parsed deterministically — for example, understanding the overall design pattern of a complex codebase by reading source files.

Even when a cognitive extractor is used, the resulting claim must pass validation before entering the Claim Graph. The Runtime Engine never blindly trusts AI-generated output.

---

## Evidence Engine

The Evidence Engine links observations to claims.

Think of it this way. An observation says "here is a raw fact." A claim says "here is what we believe about the repository." Evidence is what connects them — it says "we believe this claim because of these observations."

Without evidence, a claim is just an ungrounded hypothesis. The Runtime Engine does not accept hypotheses. It only accepts evidence-backed claims.

Responsibilities:
- Creating Evidence objects that link observations to claims
- Tracking which observations support each claim
- Tracking which observations contradict each claim
- Preventing the same evidence from being counted multiple times (which would artificially inflate trust)
- Grouping correlated evidence (several observations that all point to the same thing do not get counted as fully independent)
- Notifying the Trust Engine when evidence changes

---

## Claim Graph

The Claim Graph is the Runtime Engine's internal knowledge model of the repository.

Every node in the graph represents one claim. Every edge represents a relationship between two claims.

Example relationships:
- "Framework = Express" DEPENDS_ON "Runtime = Node.js 18"
- "Container Orchestration = Docker Compose" USES "Container = Docker"
- "Claim: Runtime = Node.js 18" CONTRADICTS "Claim: Runtime = Python 3.11"

The graph starts empty at the beginning of every investigation. It grows as claims are added during the investigation loop.

The Claim Graph is important because repository knowledge is fundamentally relational. A framework depends on a runtime. A runtime depends on a package manager. A deployment strategy depends on containerization. Storing claims in a simple list would lose all of this relational structure. The graph preserves it.

When a claim's trust level changes significantly, the graph allows the Trust Engine to propagate that change to related claims. If the claim "Runtime = Node.js 18" becomes highly trusted, the claims that depend on it (the framework, the package manager, the deployment) also get a trust boost.

---

## Trust Engine

The Trust Engine computes and maintains the trust level for every claim.

Trust is the answer to this question: "How strongly should we believe this claim based on everything we have observed?"

Trust is not assigned by the agent. Trust is not a number the LLM provides. Trust is calculated by the Runtime Engine using real evidence.

The Trust Engine considers:

**Supporting evidence**: How many observations support this claim? How diverse are those observations (do they come from different files, different execution results, or are they all just mentions in documentation)?

**Contradictory evidence**: Are there observations that contradict this claim? How strong is the contradicting evidence?

**Source reliability**: An execution result (empirical evidence) is more reliable than a documentation mention (declarative evidence). The Trust Engine weights these differently.

**Graph relationships**: If strongly trusted claims support this claim through graph relationships, that provides a small trust boost.

Trust changes throughout the investigation as new evidence arrives. A claim that starts with low trust because it was only mentioned in a README can gain high trust if execution later confirms it directly.

Contradictions are expected and normal. Repositories often contain inconsistent information — the README says one thing, the Dockerfile says another, and the actual execution behavior is a third thing. The Trust Engine records all of this. Contradictions are clearly documented in the final report.

---

## Goal Engine

The Goal Engine manages what the investigation is trying to accomplish.

Every investigation has goals. Goals are internal runtime objects — they are not the same as user commands. A user running `wizard verify runtime` creates an intent. The Runtime Engine converts that intent into one or more goals.

Goals have states:
- **Waiting** — Not yet started
- **Investigating** — Evidence is being gathered
- **Partially Verified** — Some evidence exists but more is needed
- **Verified** — Sufficient evidence has been collected
- **Blocked** — Cannot proceed because a prerequisite goal is unresolved
- **Failed** — Cannot be satisfied with available resources

Goals can also be created dynamically during the investigation. If the Runtime Engine discovers a `Dockerfile` mid-investigation, it creates a new Docker verification goal even though the user never mentioned Docker.

Goals can depend on other goals. For example, "Verify API Deployment" might depend on "Verify Container Runtime" and "Verify Node.js Runtime." The Goal Engine understands these dependencies and sequences the investigation accordingly.

---

## Priority Engine

The Priority Engine decides where the agent should focus next.

The agent does not wander randomly through the repository. The Priority Engine tells the Runtime Engine which goal is most important to investigate in the current iteration, and the Runtime Engine includes this recommendation in the Investigation Context it sends to the agent.

The Priority Engine considers:
- Which goals are active and unsatisfied
- How much uncertainty remains for each goal
- Which goals have dependencies that must be resolved first
- How much budget remains
- Whether previous attempts to address a goal have failed
- How much new information is likely to be gained from investigating each goal

The Priority Engine balances two competing needs. Exploitation means focusing on the most valuable, uncertain goals. Exploration means looking at parts of the repository that have not been examined yet. Too much exploitation causes the investigation to get stuck. Too much exploration wastes budget.

---

## Report Generator

The Report Generator assembles the final Verification Report.

When the investigation converges, the Report Generator reads from every Runtime Engine subsystem to assemble a comprehensive document. It reads:
- Verified claims from the Claim Graph
- Evidence linking those claims to observations
- Trust levels for each claim
- Completed and failed goals
- Contradictions that were detected
- Execution history and results
- Recommendations derived from the investigation

The Report Generator never invents information. Every statement in the report must be backed by verified evidence from the Runtime Engine. The report documents what was found, why the Runtime Engine believes it, and what remains uncertain.

The report is saved as `verification_report.md`. The full structure of the report is described in `verification-report.md`.

---

## The Runtime Is Technology Independent

One of the most important architectural principles is that the Runtime Engine must never contain hardcoded knowledge about specific technologies.

Wrong approach:
```
if "package.json" is found:
    run npm install
    check for Express
```

Right approach:
```
Runtime discovers "package.json" during Knowledge Discovery
↓
Runtime queries Knowledge Registry
↓
Knowledge Registry returns: Node.js Knowledge Module handles this
↓
Runtime activates Node.js Knowledge Module
↓
Node.js module provides extractors, goal templates, and verification rules
↓
Runtime uses these to investigate without knowing what Node.js is
```

The Runtime Engine knows how to investigate. Knowledge Modules know what to investigate. This separation keeps the Runtime Engine stable and maintainable as Wizard grows to support more technologies.

---

## Implementation Order

If you are building the Runtime Engine (Shivam), the recommended order is:

1. Runtime Kernel — without this, nothing else can coordinate
2. Investigation Manager — without this, investigations cannot be created
3. Repository Manager — without this, the repository cannot be accessed
4. Tool Runtime — without this, observations cannot be collected
5. Sandbox Manager — the Tool Runtime needs this to execute safely
6. Observation Engine — without this, tool outputs cannot be stored
7. Event Bus — other subsystems need this to communicate
8. Extractor Framework — without this, observations cannot become claims
9. Evidence Engine — without this, observations cannot be linked to claims
10. Claim Graph — without this, claims cannot be stored
11. Trust Engine — without this, trust cannot be computed
12. Goal Engine — without this, goals cannot be managed
13. Priority Engine — without this, the agent has no direction
14. Knowledge Registry — can be stubbed early, completed later
15. Report Generator — can be completed last

Build a minimal working version of each subsystem before moving to the next. Do not try to build everything perfectly before connecting the pieces.
