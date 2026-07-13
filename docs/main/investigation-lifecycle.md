# Investigation Lifecycle

This document explains what happens during a single investigation from the moment the user runs a command to the moment the verification report is produced.

---

## Overview

An investigation is what Wizard calls one complete repository verification session. Everything Wizard does happens inside an investigation. Every investigation follows the same lifecycle regardless of which command the user ran, which repository is being analyzed, or which technologies the repository uses.

The lifecycle is a deterministic state machine. The Runtime Engine controls every state transition. The agent cannot skip states or force the investigation to end prematurely.

---

## The Complete Lifecycle

```
State 1: Created
      ↓
State 2: Knowledge Discovery
      ↓
State 3: Goal Generation
      ↓
State 4: Agent Investigation     ←─────────────────────┐
      ↓                                                 │
State 5: Observation Collection                         │
      ↓                                                 │
State 6: Evidence Processing                            │
      ↓                                                 │
State 7: Claim Graph Update                             │
      ↓                                                 │
State 8: Trust Evaluation                               │
      ↓                                                 │
State 9: Goal Evaluation                                │
      ↓                                                 │
      ├─── Goals still active? ───────────────────────→─┘
      │
      └─── All goals converged?
            ↓
State 10: Report Generation
      ↓
State 11: Completed
```

---

## State 1: Created

The CLI submits an Investigation Request to the Runtime Engine. The Investigation Request contains:

- The repository location
- The user's intent (investigate, verify, explain, or report)
- The investigation targets (for example, "runtime" or "security")
- Configuration options
- The requested report format

The Runtime Engine validates this request. If it is valid, the Investigation Manager creates a new Investigation object.

The Investigation object starts with:
- A unique Investigation ID
- The user's intent
- The repository information
- An empty Observation Store
- An empty Claim Graph
- An empty Evidence Store
- An empty Goal List
- An investigation budget (limits how many tool executions can happen)

At this point, the repository has not been analyzed yet. The investigation exists but has not started.

---

## State 2: Knowledge Discovery

The Runtime Engine begins a lightweight scan of the repository. The goal of this phase is not to verify anything — it is to answer one simple question: what technologies appear to be present?

The Runtime Engine looks for signals like:

| Signal | What It Suggests |
|---|---|
| `package.json` | Node.js project |
| `requirements.txt` or `setup.py` | Python project |
| `pom.xml` | Java / Maven project |
| `Dockerfile` | Docker containerization |
| `docker-compose.yml` | Docker Compose orchestration |
| `.github/workflows/` | GitHub Actions CI/CD |
| `terraform/` or `.tf` files | Terraform infrastructure |
| `kubernetes/` or `.yaml` manifests | Kubernetes deployment |
| `Cargo.toml` | Rust project |

This phase is intentionally fast and cheap. The Runtime Engine only reads directory listings and file names at this stage. It does not read file contents in depth.

After this scan, the Runtime Engine asks the Knowledge Registry: "Which Knowledge Modules are relevant for this repository?" The Registry returns the matching modules. The Runtime Engine activates them.

---

## State 3: Goal Generation

With the relevant Knowledge Modules activated, the Runtime Engine creates the initial Goal set.

Goals come from two sources:

**Source 1: User Intent**

If the user ran `wizard verify runtime`, there will be a goal called "Verify Runtime." If the user ran `wizard investigate security`, there will be a goal called "Investigate Security."

**Source 2: Knowledge Module Templates**

Each activated Knowledge Module contributes goal templates. For example:

- The Docker module contributes "Verify Docker Build" and "Verify Container Runtime"
- The Node.js module contributes "Verify Node.js Dependencies" and "Verify Startup Script"
- The GitHub Actions module contributes "Verify CI Configuration"

Notice that the user only asked to "verify runtime" but the investigation now has goals for Docker, Node.js, and CI. The Runtime Engine generated these automatically because they are relevant to understanding whether the runtime actually works.

This is called dynamic goal generation. The investigation expands naturally as new information is discovered. The user does not have to specify every detail — the Runtime Engine figures out what needs to be investigated.

---

## State 4: Agent Investigation

The Runtime Engine prepares an Investigation Context and sends it to the Explorer Agent.

The Investigation Context contains:

- The list of active goals
- The current state of the Claim Graph (what is already known)
- The list of missing evidence (what gaps exist)
- The investigation history (what has already been tried)
- The list of previously failed actions
- The available tools
- The remaining budget
- Repository metadata

The Explorer Agent reads this context and decides what to investigate next. It returns exactly one Tool Request. A Tool Request says something like: "Read the file at `package.json`" or "Execute the command `npm install`" or "Search for files named `.env`."

The agent decides what to investigate by reasoning about what would most help satisfy the active goals given what is currently known and unknown.

---

## State 5: Observation Collection

The Runtime Engine receives the Tool Request from the agent. It validates the request before executing anything. Validation checks:

- Is this tool registered and available?
- Are the parameters valid?
- Does the sandbox support this operation?
- Is there enough budget remaining?
- Has this exact operation already been tried recently without success?

If validation passes, the Sandbox Manager creates an isolated execution environment. The requested tool runs inside this sandbox. The repository is treated as untrusted and cannot affect the host system.

After execution, the Sandbox Manager captures everything that happened:
- Standard output
- Standard error
- Exit code
- Generated files
- Execution duration
- Resource usage

The Observation Engine converts these raw outputs into one or more Observations. Each Observation is an immutable record — it cannot be modified after creation. Every Observation gets:

- A unique Observation ID
- A timestamp
- The source (which tool produced it)
- The type (file content, command output, error message, etc.)
- The raw payload (the actual data)
- The repository location it relates to
- The Investigation ID

Observations are the permanent evidence trail. Every conclusion in the final report can ultimately be traced back to specific observations.

---

## State 6: Evidence Processing

Raw observations need to be converted into structured knowledge. This happens through the Extractor Framework.

The Extractor Framework looks at each new observation and decides which extractor should process it.

### Deterministic Extractors

Deterministic extractors work on observations with well-defined structure. They do not use AI. They always produce the same output for the same input.

Examples:
- A JSON extractor reads `package.json` and creates a claim for each dependency listed
- A Dockerfile extractor reads a Dockerfile and creates claims about the base image, exposed ports, and startup commands
- A YAML extractor reads a `docker-compose.yml` and creates claims about each defined service

### Cognitive Extractors

Cognitive extractors use an LLM when the information cannot be extracted through deterministic rules alone. Examples include understanding what the overall architecture of the repository is, or understanding what a complex script is doing.

Even when a cognitive extractor is used, the resulting claims must pass validation before entering the Claim Graph. The Runtime Engine does not blindly trust what the LLM says.

---

## State 7: Claim Graph Update

Validated claims are added to the Claim Graph.

The Claim Graph is the Runtime Engine's internal model of the repository. Every claim is a node. Relationships between claims are edges.

For example:
- Claim: "Runtime = Node.js 18" with a DEPENDS_ON edge to "Package Manager = npm"
- Claim: "Framework = Express 4.18" with a DEPENDS_ON edge to "Runtime = Node.js 18"
- Claim: "Deployment = Docker" with a USES edge to "Container Image = node:18-alpine"

The graph grows with every iteration of the investigation loop. It starts empty and becomes more detailed as more observations are collected.

Contradictions are also recorded in the graph. If one observation suggests the runtime is Python and another suggests it is Node.js, both claims exist in the graph with a CONTRADICTS relationship between them. The Trust Engine will later resolve this.

---

## State 8: Trust Evaluation

The Trust Engine recalculates the trust level for every claim affected by the new evidence.

Trust is not a number the agent assigns. It is a value the Runtime Engine computes based on all available evidence. The Trust Engine considers:

- **How many independent observations support the claim?** (More independent sources = higher trust)
- **How reliable is the source?** (Execution results are more reliable than documentation)
- **Are there contradictions?** (Contradictory evidence reduces trust)
- **Have related claims been verified?** (A claim that is consistent with other verified claims gets a small boost)

Trust evolves throughout the investigation. A claim that starts with low trust because it was only mentioned in documentation gains much higher trust if execution later confirms it.

---

## State 9: Goal Evaluation

The Goal Engine reviews every active goal and asks: has this goal been satisfied by the current evidence?

A goal is satisfied when:
- All required claims for that goal have sufficient trust
- No significant contradictions remain unresolved
- The evidence diversity is adequate (multiple independent sources support the conclusion)

If a goal is satisfied, it is marked as complete. If a goal needs more evidence, it remains active. If the discovery of a new claim has revealed something new that needs investigation, a new goal is created.

After goal evaluation, the Priority Engine determines what should be investigated next. It ranks all active, unsatisfied goals based on their importance, the amount of uncertainty they contain, and the likelihood that additional investigation will yield useful information.

The loop then repeats from State 4.

---

## State 10: Report Generation

The investigation enters report generation when convergence is reached.

Convergence happens when:
- All primary goals have been satisfied with sufficient evidence
- No significant unresolved contradictions remain
- The Priority Engine determines that additional investigation would provide little new value

At this point, the Report Generator reads the entire verified state from the Runtime Engine and assembles the Verification Report. The report is saved as `verification_report.md`.

The format of the Verification Report is described in detail in `verification-report.md`.

---

## State 11: Completed

The investigation is marked as complete. All investigation-specific state is retained for traceability but no longer active. The user can inspect any part of the investigation history.

---

## Early Termination

Investigations can end before convergence in two ways.

### Budget Exhausted

Every investigation has a budget — a limit on how many tool executions can happen. This prevents investigations from running indefinitely on large or complex repositories.

When the budget runs out, the Runtime Engine stops the investigation loop gracefully. The Report Generator produces a partial report that explains what was successfully investigated, what was not investigated, and why.

### User Cancellation

The user can cancel an investigation at any time. The Runtime Engine catches the cancellation signal and produces the best report possible from whatever evidence has been collected so far.

---

## Investigation Independence

Every investigation is completely independent. Two investigations of the same repository never share runtime state. This means:

- Observations from one investigation never appear in another
- Claims from one investigation are not reused in another
- Trust values are calculated fresh for every investigation
- Goals are generated fresh for every investigation

What is shared across investigations is only the reusable, technology-independent knowledge in the Knowledge Modules. The modules themselves do not store any investigation-specific state.

This design guarantees that every investigation produces an accurate snapshot of the repository at the time it was run, without contamination from previous investigations.
