# Investigation Lifecycle

This document explains what happens during a single investigation from the moment the user runs a command to the moment the verification report is produced. This is the complete lifecycle of the two-graph architecture.

---

## Overview

An investigation is one complete repository verification session. Every investigation follows the same deterministic lifecycle. The Runtime Engine controls every state transition.

The investigation maintains two graphs simultaneously:

- **Knowledge Graph** — grows as claims are verified
- **Investigation Graph** — grows as the Planner creates new investigation steps

---

## The Complete Lifecycle

```
State 1: Created
      ↓
State 2: Repository Scan (Repository Manifest produced)
      ↓
State 3: Initial Planning (Technology Plan + root Investigation Graph)
      ↓
State 4: Investigation Loop  ←─────────────────────────────┐
           │                                                │
           ├─ 4a: Next Investigation Node selected          │
           ├─ 4b: Node executed (sandbox)                   │
           ├─ 4c: Observation created                       │
           ├─ 4d: Hypothesis evaluated                      │
           ├─ 4e: Claim created → Knowledge Graph updated   │
           ├─ 4f: Trust recalculated                        │
           ├─ 4g: Goal Checkpoint evaluated                 │
           ├─ 4h: Planner creates next node(s)              │
           └─────────────────────────────────────────────→─┘
                    (repeat until convergence)
      ↓
State 5: Report Generation
      ↓
State 6: Completed
```

---

## State 1: Created

The CLI submits an Investigation Request to the Runtime Engine. The Investigation Manager creates a new Investigation object with:

- A unique Investigation ID
- The user's intent (investigate, verify, explain, or report)
- An empty Knowledge Graph
- An empty Investigation Graph
- An empty Observation Store
- An investigation budget (maximum node executions)

---

## State 2: Repository Scan

The Repository Manager loads the repository. The Fast Scanner performs a lightweight scan — no file contents are read at this stage.

The Fast Scanner collects:
- The complete directory tree
- File names and extensions
- File sizes
- Presence of well-known signal files (`package.json`, `Dockerfile`, `requirements.txt`, `.github/`, etc.)

The output is the **Repository Manifest** — a compact, structured summary of the repository's surface. Typically 200 to 500 tokens. This manifest is the only thing the Planner receives for its initial call.

No analysis has occurred yet. No claims exist. The repository contents have not been read.

---

## State 3: Initial Planning

The Runtime Engine calls the Investigation Planner with:
- The Repository Manifest
- The user's intent
- The investigation targets

The Planner calls the LLM and receives back a **Technology Plan** — a structured JSON document listing the technologies it believes are present, the goals that should be created for each, and the key files that should be read first.

Example Technology Plan:
```json
{
  "technologies": [
    {
      "name": "Node.js",
      "confidence": "high",
      "signals": ["package.json", "src/*.ts"],
      "initial_goals": ["Verify Runtime", "Verify Dependencies"],
      "priority_files": ["package.json", "tsconfig.json"]
    },
    {
      "name": "Docker",
      "confidence": "high",
      "signals": ["Dockerfile", "docker-compose.yml"],
      "initial_goals": ["Verify Docker Build", "Verify Container Runtime"],
      "priority_files": ["Dockerfile", "docker-compose.yml"]
    }
  ]
}
```

The Runtime Engine uses this Technology Plan to:
1. Create the initial Goal set
2. Create the root nodes of the Investigation Graph (one Checkpoint Node per goal, plus initial Read Nodes for each priority file)

The Investigation Graph now exists. It has a small number of nodes. The Knowledge Graph is still empty.

---

## State 4: Investigation Loop

The investigation loop repeats until convergence. Each iteration executes one Investigation Node.

### Step 4a: Select Next Node

The Priority Engine selects the next Investigation Node to execute. It considers:
- Which nodes have all their dependencies satisfied
- Which goal is most in need of evidence
- The investigation budget remaining

### Step 4b: Execute the Node

The node is executed inside the Sandbox. What happens depends on the node type:

- **Read Node** → file contents are read from the repository
- **Execute Node** → a command is run inside the isolated sandbox
- **Discovery Node** → a pattern search is performed
- **Parse Node** → a previously read file is processed
- **Verify Node** → a specific claim is tested against evidence
- **Planner Node** → the Planner LLM is called to create next nodes
- **Checkpoint Node** → goal satisfaction is evaluated

### Step 4c: Observation Created

Every node execution produces an Observation. The Observation Engine converts the raw output (file contents, command output, exit code, etc.) into an immutable Observation record.

The Observation is stored permanently. It cannot be modified. Every future claim that references this information can be traced back to this Observation.

### Step 4d: Hypothesis Evaluated

This step is what makes Wizard's investigation loop efficient.

Every Investigation Node was created with a hypothesis — what the Planner expected to find. The Runtime Engine evaluates the actual result against the hypothesis:

**Expected outcome — deterministic evaluation:**

If `npm install` exits with code 0 and the hypothesis was "dependencies install without errors," the Runtime creates the success claim immediately. No LLM call. No ambiguity.

If `npm install` exits with a non-zero code and the hypothesis was the same, the Runtime creates the failure claim immediately. No LLM call.

**Unexpected outcome — Planner consulted:**

If `npm install` exits with code 0 but produces unexpected output that doesn't match the hypothesis pattern (for example, a custom package manager was used, or workspaces are configured in an unusual way), the Runtime escalates to the Planner for interpretation.

In practice, most node evaluations are expected outcomes. The Planner is called far less frequently during the loop than at the start of the investigation.

### Step 4e: Claim Created and Knowledge Graph Updated

The Extractor Framework converts the Observation into one or more Claims.

**Deterministic extraction** handles structured data — JSON files, YAML files, Dockerfiles, exit codes. No LLM needed.

**Cognitive extraction** (using the Planner's LLM) handles ambiguous data — source code meaning, natural language documentation, complex output interpretation. Used only when deterministic extraction is insufficient.

Validated Claims are added to the Knowledge Graph as nodes. Relationships between claims are added as edges. The Knowledge Graph grows.

The Investigation Graph node that produced this claim is linked to the claim. This creates the complete audit trail: every claim in the Knowledge Graph points back to the Investigation Graph node that created it, which points back to the Observation that triggered it.

### Step 4f: Trust Recalculated

The Trust Engine recalculates the trust level for every claim affected by the new evidence.

Trust increases when independent sources confirm the same claim. Trust decreases when contradictions appear. Execution results carry higher trust weight than documentation. The Trust Engine also propagates trust changes through the Knowledge Graph — if a highly trusted claim is updated, related claims are also affected.

### Step 4g: Goal Checkpoint Evaluated

The Goal Engine checks each active Checkpoint Node: has sufficient evidence been collected to satisfy this goal?

A goal is satisfied when:
- All required claims are present in the Knowledge Graph
- Those claims have sufficient trust
- No unresolved contradictions remain for critical claims

If a goal is satisfied, its Checkpoint Node is marked complete. If not, the investigation continues.

### Step 4h: Planner Creates Next Nodes

The Planner is called with a compact summary of the current investigation state — the recent Investigation Graph nodes, the current Knowledge Graph state for active goals, and what evidence is still missing.

The Planner creates one or more new Investigation Nodes and returns them to the Runtime Engine. These nodes are added to the Investigation Graph.

The Planner at this stage is making small, targeted decisions: "Given that npm install succeeded and the entry point is server.js, the next step should be to execute server.js and verify it starts on a port." It creates one Execute Node with a specific hypothesis.

The loop returns to Step 4a.

---

## Investigation Graph Growth Example

Here is what the Investigation Graph looks like for `wizard verify runtime` on a Node.js + Docker project, showing how nodes are added dynamically:

```
Start:
  Checkpoint: Verify Runtime [waiting]
  Checkpoint: Verify Docker Runtime [waiting]

After initial Planner call:
  Checkpoint: Verify Runtime [waiting]
  ├── Read: package.json [ready]
  └── Discovery: entry point files [ready]
  Checkpoint: Verify Docker Runtime [waiting]
  ├── Read: Dockerfile [ready]
  └── Read: docker-compose.yml [ready]

After package.json read:
  Read: package.json [complete]
  ├── Parse: extract scripts.start [complete] → Claim: Entry = server.js
  ├── Execute: npm install [ready]
  └── Execute: node server.js [blocked: needs npm install]

After npm install:
  Execute: npm install [complete] → Claim: Dependencies = installable
  └── Execute: node server.js [ready]

After node server.js:
  Execute: node server.js [complete] → Claim: Runtime verified, port 3000
  └── Checkpoint: Verify Runtime [satisfied ✓]

(Docker nodes following a similar pattern in parallel)
```

Notice that none of these nodes existed when the investigation started. The graph grew entirely from the evidence that was collected. The investigation adapted to what it found.

---

## Convergence

The investigation converges when:
- All active Checkpoint Nodes are satisfied
- No significant unresolved contradictions exist
- The Priority Engine determines that additional investigation would provide little new value

When convergence is reached, the investigation moves to Report Generation.

---

## Early Termination

**Budget exhausted:** When the maximum node execution count is reached, the Runtime stops gracefully. The Report Generator produces a partial report explaining what was successfully investigated, what remains uncertain, and why.

**User cancellation:** The Runtime catches the signal and produces the best possible report from current evidence.

**Fatal failure:** Sandbox unavailable, or similar. The Runtime records the failure as an Observation and produces a partial report.

---

## State 5: Report Generation

The Report Generator reads from both graphs:
- The Knowledge Graph provides all verified claims with their trust levels
- The Investigation Graph provides the complete execution history and audit trail
- The Observation Store provides the raw evidence

The Report Generator assembles the Verification Report. Every statement references the claims that support it. Every claim references the Investigation Graph nodes that produced it. Every node references the Observations it collected.

The report is saved as `verification_report.md`.

---

## State 6: Completed

The investigation is archived. All state is retained for traceability. The complete Investigation Graph can be inspected to understand exactly how every conclusion was reached — which files were read in what order, which commands were run, which hypotheses were confirmed or refuted, and how trust evolved throughout.
