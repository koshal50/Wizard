# Wizard — Context Engine Architecture (Final)

## Runtime Engine Harness: End-to-End Context System Design

---

## Table of Contents

1. [Foundational Principles](#1-foundational-principles)
2. [System Overview](#2-system-overview)
3. [Investigation State — The Source of Truth](#3-investigation-state--the-source-of-truth)
4. [Investigation Event Log — The Append-Only Audit Trail](#4-investigation-event-log--the-append-only-audit-trail)
5. [Context Engine Architecture — Seven Stages](#5-context-engine-architecture--seven-stages)
6. [Stage 1: Reader](#6-stage-1-reader)
7. [Stage 2: Filter](#7-stage-2-filter)
8. [Stage 3: Compressor](#8-stage-3-compressor)
9. [Stage 4: Packager — Modular Context Sections](#9-stage-4-packager--modular-context-sections)
10. [Stage 5: Interceptor — Context Rewrite and Rejection](#10-stage-5-interceptor--context-rewrite-and-rejection)
11. [Stage 6: Budget Manager — With KV Cache Optimization](#11-stage-6-budget-manager--with-kv-cache-optimization)
12. [Stage 7: Context Cache and Audit](#12-stage-7-context-cache-and-audit)
13. [The Three Context Structures](#13-the-three-context-structures)
14. [Structured Investigation Lifecycle](#14-structured-investigation-lifecycle)
15. [Complete Investigation Step Flow](#15-complete-investigation-step-flow)
16. [Evidence Chain & Traceability](#16-evidence-chain--traceability)
17. [Trust Score Computation](#17-trust-score-computation)
18. [Runtime Invariant Enforcement](#18-runtime-invariant-enforcement)
19. [Context Injection — Async Context Updates](#19-context-injection--async-context-updates)
20. [Investigation Fork and Resume](#20-investigation-fork-and-resume)
21. [Persistence & Serialization](#21-persistence--serialization)
22. [API Surface — Class Reference](#22-api-surface--class-reference)
23. [Design Decisions & Tradeoffs](#23-design-decisions--tradeoffs)
24. [Viva-Ready Defense](#24-viva-ready-defense)

---

## 1. Foundational Principles

The Context Engine is built on six distinctions that separate it from naive context management:

| Principle | Meaning | Consequence for Context Engine |
|-----------|---------|-------------------------------|
| **Context ≠ Memory** | Context is ephemeral supply. Memory is persistent state. | The engine constructs context FROM state. Agents never store context between calls. |
| **Summaries destroy causal history** | Repeated summarization preserves conclusions while removing the reasoning that produced them. | Compression preserves provenance links (observation IDs, claim IDs) alongside every summary. |
| **Information ≠ Belief** | "Express exists" is information. "Express is the primary framework" is a belief requiring evidence. | Context separates verified claims (with evidence links) from unverified assumptions (labeled explicitly). |
| **Confidence ≠ Evidence** | An LLM can be 99% confident and still be wrong. | Trust scores are computed by deterministic algorithms in the Runtime Engine, never by the LLM. |
| **Assumptions should be visible** | Hidden assumptions cause cascading failures — the agent builds internally consistent but wrong work. | Context always surfaces unverified hypotheses alongside verified facts, labeled distinctly. |
| **Capability ≠ Authorization** | Knowing what to execute is not the same as being permitted to execute it. | Context shows available tools, but the Runtime Engine validates and authorizes every execution. |

### The Central Question

> How do I supply each reasoning component with exactly the information it needs to make one good decision, without destroying the causal history that produced the current state, without wasting tokens on irrelevant data, and without letting summarization eat the reasoning trail?

---## 2. System Overview

### Where the Context Engine Sits

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         WIZARD ARCHITECTURE                             │
│                                                                         │
│  User → CLI → Runtime Engine ← Investigation Planner                    │
│                     │                                                   │
│              ┌──────▼──────┐                                           │
│              │  Context     │                                           │
│              │  Engine      │                                           │
│              │              │                                           │
│              │  Reader     │  ← Reads from InvestigationState           │
│              │  ↓          │                                             │
│              │  Filter     │  ← Selects relevant slices                 │
│              │  ↓          │                                             │
│              │  Compressor │  ← Shrinks without destroying causality    │
│              │  ↓          │                                             │
│              │  Packager   │  ← Assembles modular context sections       │
│              │  ↓          │                                             │
│              │  Interceptor│  ← Rewrite or reject before agent sees it   │
│              │  ↓          │                                             │
│              │  BudgetMgr  │  ← Enforces token limits + KV cache order   │
│              │  ↓          │                                             │
│              │  Cache      │  ← Avoids redundant construction            │
│              │  ↓          │                                             │
│              │  Audit      │  ← Records what was supplied                │
│              └──────┬──────┘                                           │
│                     │                                                   │
│            ┌────────┼────────┐                                         │
│            ▼        ▼        ▼                                         │
│      Explorer  Verifier  Planner                                      │
│      Context   Context   Context                                      │
│                                                                         │
│  Everything routes through the Runtime Engine.                          │
│  Nothing bypasses it.                                                   │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### What the Context Engine Is and Is Not

| Is | Is Not |
|----|--------|
| A read-only projection layer over InvestigationState | A storage system |
| A discriminator that selects relevance | A data dump |
| A compressor that preserves causality | A summarizer that discards history |
| A packager that tailors context per agent | A one-size-fits-all prompt builder |
| A budget enforcer with KV cache awareness | A state mutator |
| An interception point for context validation | A passive pipeline |

### Core Invariants

1. **The Context Engine never mutates InvestigationState.** It reads, filters, compresses, and packages.
2. **Every piece of context is traceable to a source in state.** Observation IDs, claim IDs, and node IDs are always carried.
3. **Agents are stateless.** They receive context, return a decision, and forget everything. The Runtime Engine owns all state.
4. **Three agents, three context structures.** Explorer, Verifier, and Planner each receive a different context tailored to their role.
5. **Compression never drops provenance.** Summaries always carry observation IDs and claim IDs for traceability.
6. **The Investigation Event Log records every state mutation.** The log is the append-only audit trail.
7. **Runtime Invariants verify reconstructability.** After every mutation, state must be reconstructable from the event log.

---## 3. Investigation State — The Source of Truth

The Context Engine reads from a single `InvestigationState` object owned by the Runtime Engine. This is the only source of truth for random-access queries. The Investigation Event Log (§4) runs alongside it as the append-only audit trail.

### 3.1 State Structure

```
InvestigationState {
  // ─── Identity ─────────────────────────────────────────────
  investigation_id: UUID
  intent: {
    action: "verify" | "investigate"
    target: "runtime" | "architecture" | "dependencies" | "security" | string
  }
  phase: "DISCOVERY" | "PLANNING" | "EXECUTING" | "VERIFYING" | "CONVERGED" | "EXHAUSTED"
  created_at: ISO8601Timestamp
  last_updated: ISO8601Timestamp

  // ─── Repository Discovery ─────────────────────────────────
  repository_manifest: RepositoryManifest

  // ─── The Three Graphs (in-memory, transient during execution) ─
  investigation_graph: DAG<InvestigationNode>
  knowledge_graph: PropertyGraph<KnowledgeNode, KnowledgeEdge>
  claim_graph: PropertyGraph<Claim, ClaimEdge>

  // ─── Immutable Stores (append-only) ───────────────────────
  observations:      Map<ObservationID, Observation>
  execution_history: List<ToolExecution>
  event_log:         List<RuntimeEvent>

  // ─── Budget ───────────────────────────────────────────────
  budget: {
    total: number           // Total tool-call budget for this investigation
    remaining: number       // Remaining budget
    cost_per_call: number   // Cost deducted per tool call (default: 1)
  }

  // ─── Goals ────────────────────────────────────────────────
  active_goals: List<InvestigationGoal>
  goal_status: Map<GoalID, GoalStatus>

  // ─── Agent Interaction History ────────────────────────────
  agent_calls: List<AgentCallRecord>

  // ─── Verifier State ───────────────────────────────────────
  verifier_rounds: number
  verifier_interval: number
  last_verifier_recommendations: List<VerifierRecommendation>

  // ─── Context Injection Queue ──────────────────────────────
  context_injection_queue: List<ContextInjection>
}
```

### 3.2 Core Data Structures

```
InvestigationNode {
  id: string
  type: "read_file" | "execute_command" | "check_port" | "search_repository" | "verify_claim" | string
  description: string
  hypothesis: string
  status: "PENDING" | "EXECUTING" | "COMPLETED" | "FAILED" | "SKIPPED" | "BLOCKED"
  dependencies: List<NodeID>
  observations: List<ObservationID>
  claims: List<ClaimID>
  created_at: ISO8601Timestamp
  completed_at: ISO8601Timestamp | null
}

KnowledgeNode {
  id: string
  type: "technology" | "file" | "directory" | "service" | "dependency" | "port" | string
  name: string
  category: string
  properties: Map<string, any>
  verified: boolean
  evidence_count: number
  observation_ids: List<ObservationID>
}

KnowledgeEdge {
  from: NodeID
  to: NodeID
  type: "DEPENDS_ON" | "RUNS_IN" | "USES" | "DEPLOYS_TO" | "CONTAINS" | "COMMUNICATES_WITH" | string
  verified: boolean
}

Claim {
  id: string
  statement: string
  trust_score: number         // 0.0 to 1.0, computed deterministically
  status: "UNVERIFIED" | "VERIFIED" | "CONTRADICTED" | "PARTIAL"
  provenance: {
    derived_from_observations: List<ObservationID>
    derived_from_claims: List<ClaimID>
    agent: "explorer" | "verifier" | "runtime"
  }
  supporting_claims: List<ClaimID>
  contradicting_claims: List<ClaimID>
  created_at: ISO8601Timestamp
  last_updated: ISO8601Timestamp
}

Observation {
  id: string
  tool: string
  parameters: Map<string, any>
  raw_output: string          // Full raw output — immutable
  exit_code: number | null
  duration_ms: number
  success: boolean
  node_id: string | null
  timestamp: ISO8601Timestamp
}

ToolExecution {
  id: string
  tool_request: ToolRequest
  validation_result: ValidationResult
  observation_id: string | null
  status: "VALIDATED" | "EXECUTED" | "FAILED"
  timestamp: ISO8601Timestamp
}

ToolRequest {
  tool: string
  parameters: Map<string, any>
  reasoning: string
  node_id: string
}

AgentCallRecord {
  id: string
  agent: "explorer" | "verifier" | "planner"
  context_summary: string
  context_token_count: number
  response: any
  duration_ms: number
  timestamp: ISO8601Timestamp
}

GoalStatus {
  goal_id: string
  description: string
  status: "PENDING" | "IN_PROGRESS" | "VERIFIED" | "FAILED" | "PARTIAL"
  trust_score: number
  verified_claim_count: number
  unverified_claim_count: number
  last_updated: ISO8601Timestamp
}

RuntimeEvent {
  type: string
  timestamp: ISO8601Timestamp
  data: any
}

ContextInjection {
  id: string
  section: ContextSection
  target_agent: "explorer" | "verifier" | "planner"
  injected_by: "verifier" | "planner" | "runtime"
  timestamp: ISO8601Timestamp
  consumed: boolean
}
```

---## 4. Investigation Event Log — The Append-Only Audit Trail

The Investigation Event Log runs alongside the Investigation State stores. It is an append-only event stream that records every mutation to the investigation. This serves three purposes:

1. **Audit Trail** — Every change is recorded with sequence number, timestamp, and provenance.
2. **Reconstructability** — The entire InvestigationState can be reconstructed from the log alone via `deriveInvestigationState()`.
3. **Fork and Resume** — Fork the log at any sequence number to create an alternative investigation path. Resume from any checkpoint by replaying the log.

### 4.1 Event Structure

```
InvestigationEvent {
  type: string,       // See event types below
  seq: number,        // Monotonically increasing sequence number
  timestamp: ISO8601,
  investigation_id: UUID,
  node_id: string | null,    // Which investigation node produced this
  goal_id: string | null,    // Which goal this relates to
  data: any,          // Event-specific payload
  provenance: {       // Traceability chain
    derived_from_event_ids: List<string>,
    derived_from_observations: List<string>,
    agent: "explorer" | "verifier" | "planner" | "runtime",
  }
}
```

### 4.2 Event Types

| Type | Description | Produced By |
|------|-------------|-------------|
| `repository_manifest` | Repository discovery complete | Runtime Engine |
| `graph_created` | Investigation graph created | Planner |
| `graph_changed` | Nodes/edges added to investigation graph | Planner |
| `node_started` | Investigation node began execution | Runtime Engine |
| `node_completed` | Investigation node finished | Runtime Engine |
| `node_failed` | Investigation node failed | Runtime Engine |
| `node_skipped` | Investigation node skipped (interceptor rejection) | Interceptor |
| `tool_validated` | Tool request passed validation | Runtime Engine |
| `tool_validation_failed` | Tool request failed validation | Runtime Engine |
| `observation` | New observation recorded | Runtime Engine |
| `claim_created` | New claim generated from observation | Runtime Engine |
| `claim_updated` | Claim trust score or status changed | Runtime Engine |
| `knowledge_updated` | Knowledge graph node/edge added or modified | Runtime Engine |
| `verifier_assessment` | Verifier agent produced assessment | Verifier |
| `budget_updated` | Budget remaining changed | Runtime Engine |
| `goal_updated` | Goal status changed | Runtime Engine |
| `context_supplied` | Context was supplied to an agent | Context Engine Audit |
| `context_injected` | Context was injected into queue | Context Injector |
| `phase_changed` | Investigation phase changed | Runtime Engine |
| `investigation_converged` | Investigation reached convergence | Runtime Engine |
| `investigation_exhausted` | Investigation exhausted budget | Runtime Engine |

### 4.3 deriveInvestigationState() — Reconstruction from Log

The log can reconstruct the full InvestigationState. This is the runtime invariant:

```
deriveInvestigationState(log) → InvestigationState

Reconstruction:
  state = empty_state()

  for event of log.events {
    switch event.type {
      case "repository_manifest":
        state.repository_manifest = event.data
        break
      case "graph_created":
        state.investigation_graph = create_dag(event.data.nodes, event.data.edges)
        break
      case "graph_changed":
        for node of event.data.nodes:
          state.investigation_graph.add_node(node)
        for edge of event.data.edges:
          state.investigation_graph.add_edge(edge)
        break
      case "observation":
        state.observations.set(event.data.id, event.data)
        break
      case "claim_created":
        state.claim_graph.add_node(event.data)
        state.claim_graph.add_edges(event.data.provenance)
        break
      case "claim_updated":
        claim = state.claim_graph.get_node(event.data.id)
        apply_delta(claim, event.data)
        break
      case "knowledge_updated":
        apply_knowledge_delta(state.knowledge_graph, event.data)
        break
      case "budget_updated":
        state.budget = event.data
        break
      case "goal_updated":
        state.goal_status.set(event.data.goal_id, event.data)
        break
      case "phase_changed":
        state.phase = event.data.phase
        break
    }
  }

  // Runtime invariant: state must be fully reconstructable
  assert(state.is_consistent())

  return state
```

### 4.4 Why Both Stores AND Log?

The stores remain for **fast random-access queries** during context construction. The Reader reads from stores, not from the log — scanning a 500-event log on every step is wasteful when the stores are already in memory.

The log serves **audit, reconstruction, fork, and resume**. It is the authoritative record. The stores are the working cache. The runtime invariant ensures they stay consistent.

This is the strategic learning from DeepSeek Harness: a single append-only log as the ground truth. Wizard keeps its optimized stores for performance, but adds the log as the audit backbone — getting reconstructability and fork/resume without sacrificing query speed.

---## 5. Context Engine Architecture — Seven Stages

The seven-stage pipeline transforms InvestigationState into agent-specific context. Each stage is a read-only projection — none mutate state.

| Stage | Responsibility | Key Design |
|-------|---------------|------------|
| **1. Reader** | Extract data from state stores | Targeted queries, never raw dumps |
| **2. Filter** | Select relevant slices per agent role | Different filters for Explorer, Verifier, Planner |
| **3. Compressor** | Shrink without destroying causality | Preserve provenance, compress payload |
| **4. Packager** | Assemble modular context sections | Plugin-registered sections, not monolithic templates |
| **5. Interceptor** | Rewrite or reject before agent sees it | Waterfall listeners can modify or block context |
| **6. Budget Manager** | Enforce token limits + KV cache order | Progressive trimming, prefix-stable ordering |
| **7. Cache + Audit** | Avoid redundant construction, record supply | Versioned cache, append-only audit log |

---

## 6. Stage 1: Reader

The Reader knows how to pull data from each state component. It doesn't filter or summarize yet — it extracts raw material through targeted queries.

```
Reader {
  // ─── From Investigation Graph ────────────────────────────
  read_current_node(state, node_id): InvestigationNode
  read_graph_topology(state): { total, completed, failed, pending, blocked }
  read_execution_frontier(state): List<InvestigationNode>  // Next executable nodes
  read_blocked_nodes(state): List<InvestigationNode>
  read_failed_nodes(state): List<InvestigationNode>

  // ─── From Knowledge Graph ────────────────────────────────
  read_verified_entities(state): List<KnowledgeNode>  // Where verified = true
  read_relationships(state, entity_id): List<KnowledgeEdge>
  read_technology_stack(state): Map<category, List<string>>
  read_repository_summary(state): RepositorySummary

  // ─── From Claim Graph ────────────────────────────────────
  read_claims_by_goal(state, goal_id): List<Claim>
  read_claims_by_status(state, status): List<Claim>
  read_claim_with_provenance(state, claim_id): Claim + linked observations
  read_contradictions(state): List<{ claim_a, claim_b, edge }>
  read_unverified_claims(state): List<Claim>
  read_verified_claims(state): List<Claim>

  // ─── From Observations ───────────────────────────────────
  read_observations_for_node(state, node_id): List<Observation>
  read_observations_for_claim(state, claim_id): List<Observation>
  read_recent_observations(state, last_n: number): List<Observation>
  read_failed_observations(state, last_n: number): List<Observation>

  // ─── From Execution History ──────────────────────────────
  read_recent_executions(state, last_n: number): List<ToolExecution>
  read_failed_executions(state, last_n: number): List<ToolExecution>

  // ─── From Event Log ──────────────────────────────────────
  read_recent_events(state, last_n: number): List<RuntimeEvent>

  // ─── From Goals ──────────────────────────────────────────
  read_goal_status(state, goal_id): GoalStatus
  read_all_goal_statuses(state): Map<GoalID, GoalStatus>
  read_unsatisfied_goals(state): List<InvestigationGoal>

  // ─── From Verifier State ─────────────────────────────────
  read_verifier_recommendations(state): List<VerifierRecommendation>
  read_verifier_rounds(state): number

  // ─── From Budget ─────────────────────────────────────────
  read_budget(state): BudgetStatus
}
```

**Key principle:** The Reader exposes *queries*, not raw data dumps. Every read operation is targeted. You never read "all observations" — you read "observations for this node" or "the last 5 observations."

---## 7. Stage 2: Filter

This is where the insight about **relevance being itself a problem** matters. The Filter doesn't just pick "the most relevant things" — it picks the *right kind* of things for *the right agent*.

### Filter Strategy for Explorer Context

The Explorer needs to answer: **"What is the highest-value next action?"**

```
ExplorerFilter {
  filter(state, current_node): FilteredMaterial {
    return {
      // WHAT ARE WE TRYING TO DO RIGHT NOW
      current_node: reader.read_current_node(state, current_node.id),

      // WHAT DO WE ALREADY KNOW (verified only — don't pollute with speculation)
      verified_claims: reader.read_claims_by_status(state, "VERIFIED")
        .filter(claim => claim.relevant_to(current_node))
        .take(10),

      // WHAT DO WE SUSPECT BUT HAVEN'T PROVEN (assumptions visible)
      unverified_claims: reader.read_claims_by_status(state, "UNVERIFIED")
        .filter(claim => claim.related_to(current_node))
        .take(5),

      // WHAT EVIDENCE DO WE HAVE FOR THE CURRENT NODE
      node_observations: reader.read_observations_for_node(state, current_node.id),

      // WHAT WENT WRONG RECENTLY (so we don't repeat failures)
      recent_failures: reader.read_failed_executions(state, 3),

      // WHAT TOOLS ARE AVAILABLE FOR THIS NODE TYPE
      available_tools: resolve_tools_for_node_type(current_node.type),

      // HIGH-LEVEL REPOSITORY UNDERSTANDING
      repository_summary: reader.read_repository_summary(state),

      // BUDGET AWARENESS
      remaining_budget: state.budget.remaining,

      // INVESTIGATION PHASE
      phase: state.phase,
    }
  }
}
```

### Filter Strategy for Verifier Context

The Verifier needs to answer: **"Is the evidence sufficient, or are there gaps and contradictions?"**

```
VerifierFilter {
  filter(state, goal_id): FilteredMaterial {
    return {
      goal: reader.read_goal_status(state, goal_id),

      claims: reader.read_claims_by_goal(state, goal_id)
        .map(claim => ({
          ...claim,
          supporting_observations: reader.read_observations_for_claim(state, claim.id),
          supporting_claims: read_supporting_claim_ids(state, claim.id),
          contradicting_claims: read_contradicting_claim_ids(state, claim.id),
        })),

      contradictions: reader.read_contradictions(state),
      gaps: identify_evidence_gaps(state, goal_id),
      aggregate_trust: compute_goal_trust(state, goal_id),
      recent_events: reader.read_recent_events(state, 10),
    }
  }
}
```

### Filter Strategy for Planner Context

The Planner needs to answer: **"What should we investigate next, and in what order?"**

```
PlannerFilter {
  filter(state, is_incremental: boolean): FilteredMaterial {
    if (!is_incremental) {
      return {
        repository_manifest: state.repository_manifest,
        user_intent: state.intent,
        budget: state.budget.total,
      }
    }

    return {
      graph_summary: reader.read_graph_topology(state),
      newly_discovered: {
        technologies: get_new_technologies(state),
        files: get_new_files(state),
        directories: get_new_directories(state),
      },
      verifier_feedback: reader.read_verifier_recommendations(state),
      blocked_nodes: reader.read_blocked_nodes(state),
      failed_nodes: reader.read_failed_nodes(state),
      remaining_goals: reader.read_unsatisfied_goals(state),
      remaining_budget: state.budget.remaining,
    }
  }
}
```

---## 8. Stage 3: Compressor

This is where the insight about **summaries destroying causal history** becomes critical.

### The Problem with Naive Compression

```
BAD: "The runtime is Node.js"
     (Lost: which files were read, which commands ran, what output was observed)

BAD: "npm start succeeded"
     (Lost: what the actual output was, what port it bound to, what PID was created)

BAD: "Express framework detected"
     (Lost: that it came from package.json dependencies, not from reading source code)
```

### The Compression Strategy

**Rule 1: Compress the payload, not the provenance.**

```
Observation {
  id: "OBS-42",
  tool: "read_file",
  path: "package.json",
  raw_output: "{ \"name\": \"my-app\", \"dependencies\": { \"express\": \"^4.18.0\" } }",
  // ... 5000 more characters of raw content
  timestamp: "2024-01-15T10:30:00Z",
  exit_code: 0,
}

// BAD compression:
"package.json contains Express dependency"
// → Lost: the exact version, the exact content, the fact that it was a FILE READ

// GOOD compression:
ObservationSummary {
  id: "OBS-42",                    // Preserved — can trace back to full observation
  tool: "read_file",               // Preserved — we know HOW we got this
  path: "package.json",            // Preserved — we know WHERE
  summary: "Contains Express ^4.18.0 in dependencies",  // Compressed payload
  key_findings: ["express: ^4.18.0"],  // Structured extraction
  full_text_available: true,       // Flag — full text exists in observation store
}
```

**Rule 2: Preserve the causal chain.**

```
// BAD: Just the conclusion
"Runtime verified: Node.js"

// GOOD: The chain
EvidenceChain {
  conclusion: "Runtime = Node.js",
  trust_score: 0.92,
  chain: [
    { step: "read_file", target: "package.json", finding: "engines.node = 18" },
    { step: "execute_command", command: "node --version", finding: "v18.17.0" },
    { step: "execute_command", command: "npm start", finding: "exit_code=0" },
  ]
}
```

**Rule 3: Compress by aggregation, not by deletion.**

```
// Instead of dropping old observations:
// BAD: [keep only last 5 observations]

// Aggregate them:
ObservationAggregation {
  total_observations: 47,
  by_tool: {
    read_file: 22,
    execute_command: 18,
    check_port: 5,
    search_repository: 2,
  },
  by_outcome: {
    success: 41,
    failure: 6,
  },
  key_observations: [
    { id: "OBS-42", summary: "package.json: Express ^4.18.0" },
    { id: "OBS-58", summary: "npm start: server listening on port 3000" },
    { id: "OBS-61", summary: "port 3000: accepting connections" },
  ],
  full_store_reference: "inv_001/observations.json"  // Trace back to full store
}
```

**Rule 4: Compress observations differently based on evidential weight.**

```
CompressionPriority {
  // HIGH priority — compress minimally, preserve structure
  EXECUTION_OUTPUT: {
    // "npm start" succeeded with specific output
    // Compress to: { command, exit_code, key_output_lines }
    // Keep: exit_code, first/last 5 lines of output, any port bindings
  },

  NETWORK_EVIDENCE: {
    // Port check, HTTP response
    // Compress to: { port, status, response_summary }
    // Keep: status code, response headers summary
  },

  // MEDIUM priority — summarize content, preserve metadata
  FILE_CONTENT: {
    // package.json, Dockerfile, config files
    // Compress to: { path, key_fields_extracted }
    // Keep: file path, extracted structured data
  },

  // LOW priority — aggressive summarization
  SEARCH_RESULTS: {
    // grep results, file listings
    // Compress to: { query, match_count, representative_matches }
    // Keep: query pattern, count, top 3 matches
  },

  DIRECTORY_LISTING: {
    // Compress to: { path, file_count, notable_files }
    // Keep: path, count, files matching known patterns
  },
}
```

### The Compressor Implementation

```
Compressor {
  compress_observation(observation: Observation, priority: CompressionPriority): ObservationSummary {
    switch (priority) {
      case EXECUTION_OUTPUT:
        return {
          id: observation.id,
          tool: observation.tool,
          command: observation.parameters.command,
          exit_code: observation.exit_code,
          key_output: extract_key_lines(observation.raw_output),
          duration_ms: observation.duration_ms,
          full_available: true,
        }

      case FILE_CONTENT:
        return {
          id: observation.id,
          tool: observation.tool,
          path: observation.parameters.path,
          extracted: extract_structured_data(observation.raw_output),
          line_count: observation.raw_output.split('\n').length,
          full_available: true,
        }

      case NETWORK_EVIDENCE:
        return {
          id: observation.id,
          tool: observation.tool,
          port: observation.parameters.port,
          status: observation.parameters.status,
          response_summary: summarize_response(observation.raw_output),
          full_available: true,
        }

      case SEARCH_RESULTS:
        return {
          id: observation.id,
          tool: observation.tool,
          query: observation.parameters.query,
          match_count: count_matches(observation.raw_output),
          representative_matches: top_matches(observation.raw_output, 3),
          full_available: true,
        }

      case DIRECTORY_LISTING:
        return {
          id: observation.id,
          tool: observation.tool,
          path: observation.parameters.path,
          file_count: count_files(observation.raw_output),
          notable_files: extract_notable_files(observation.raw_output),
          full_available: true,
        }
    }
  }

  compress_claims(claims: List<Claim>, max_count: number): List<ClaimSummary> {
    return claims
      .sort((a, b) => b.trust_score - a.trust_score)
      .take(max_count)
      .map(claim => ({
        id: claim.id,
        statement: claim.statement,
        trust_score: claim.trust_score,
        status: claim.status,
        evidence_count: claim.provenance.derived_from_observations.length,
        observation_ids: claim.provenance.derived_from_observations,
      }))
  }
}
```

---## 9. Stage 4: Packager — Modular Context Sections

The Packager takes filtered + compressed material and assembles it into the exact structure each agent expects.

### Modular Section Design (Learning from DeepSeek)

Instead of monolithic templates, context is assembled from **registered sections**. Each section declares its scope, priority, and content. This makes the system extensible without modifying core templates.

```
ContextSection {
  id: string,           // "verified_claims", "recent_observations", etc.
  priority: number,     // Higher = trimmed last by Budget Manager
  scope: string,        // "all_agents" | "explorer_only" | "verifier_only" | "planner_only"
  content: string,      // The actual section text
  token_cost: number,   // Pre-computed token cost
}
```

**Built-in sections:**

| Section ID | Scope | Priority | Source |
|-----------|-------|----------|--------|
| `system_instructions` | all_agents | 100 | Hardcoded |
| `available_tools` | explorer_only | 90 | Tool Registry |
| `repository_summary` | all_agents | 80 | Knowledge Graph |
| `verified_claims` | explorer_only | 75 | Claim Graph |
| `unverified_assumptions` | explorer_only | 70 | Claim Graph |
| `recent_observations` | explorer_only | 60 | Observations |
| `recent_failures` | explorer_only | 50 | Execution History |
| `budget_status` | explorer_only | 40 | Budget |
| `claims_under_review` | verifier_only | 90 | Claim Graph |
| `contradictions` | verifier_only | 85 | Claim Graph |
| `evidence_gaps` | verifier_only | 80 | Verifier |
| `graph_topology` | planner_only | 90 | Investigation Graph |
| `verifier_feedback` | planner_only | 85 | Verifier State |
| `newly_discovered` | planner_only | 80 | Knowledge Graph |
| `blocked_nodes` | planner_only | 75 | Investigation Graph |
| `failed_nodes` | planner_only | 70 | Investigation Graph |
| `injected_context` | scoped | variable | Context Injector |

### Section Registration

```
ContextSectionRegistry {
  sections: Map<string, ContextSection> = new Map()

  register(section: ContextSection): void {
    this.sections.set(section.id, section)
  }

  unregister(section_id: string): void {
    this.sections.delete(section_id)
  }

  assemble(agent_type: string, node_type: string): List<ContextSection> {
    return Array.from(this.sections.values())
      .filter(s => this.is_in_scope(s, agent_type))
      .filter(s => this.is_compatible(s, node_type))
      .sort((a, b) => b.priority - a.priority)
  }

  is_in_scope(section: ContextSection, agent_type: string): boolean {
    if (section.scope === "all_agents") return true
    if (section.scope === "explorer_only") return agent_type === "explorer"
    if (section.scope === "verifier_only") return agent_type === "verifier"
    if (section.scope === "planner_only") return agent_type === "planner"
    return false
  }
}
```

### Packager Implementation

```
Packager {
  build_explorer_context(filtered: FilteredMaterial): List<ContextSection> {
    return [
      {
        id: "system_instructions",
        priority: 100,
        scope: "explorer_only",
        content: `
INVESTIGATION CONTEXT
=====================

GOAL: ${filtered.current_node.description}
HYPOTHESIS: ${filtered.current_node.hypothesis}
NODE TYPE: ${filtered.current_node.type}
PHASE: ${filtered.phase}

INSTRUCTION: Return a single ToolRequest with tool name, parameters, and reasoning.
`,
      },
      {
        id: "repository_summary",
        priority: 80,
        scope: "explorer_only",
        content: `
REPOSITORY OVERVIEW
-------------------
Languages: ${filtered.repository_summary.languages.join(", ")}
Frameworks: ${filtered.repository_summary.frameworks.join(", ")}
Key Files: ${filtered.repository_summary.key_files.join(", ")}
Docker: ${filtered.repository_summary.has_docker ? "Yes" : "No"}
Kubernetes: ${filtered.repository_summary.has_k8s ? "Yes" : "No"}
`,
      },
      {
        id: "verified_claims",
        priority: 75,
        scope: "explorer_only",
        content: `
VERIFIED KNOWLEDGE
------------------
${filtered.verified_claims.map(c =>
  `[${c.trust_score.toFixed(2)}] ${c.statement} (from ${c.evidence_count} observation(s))`
).join("\n")}
`,
      },
      {
        id: "unverified_assumptions",
        priority: 70,
        scope: "explorer_only",
        content: `
UNVERIFIED ASSUMPTIONS
----------------------
${filtered.unverified_claims.map(c => `? ${c.statement}`).join("\n")}
`,
      },
      {
        id: "recent_observations",
        priority: 60,
        scope: "explorer_only",
        content: `
RECENT OBSERVATIONS
-------------------
${filtered.node_observations.map(o => format_observation_summary(o)).join("\n")}
`,
      },
      {
        id: "recent_failures",
        priority: 50,
        scope: "explorer_only",
        content: `
RECENT FAILURES
---------------
${filtered.recent_failures.map(f => `FAILED: ${f.tool} → ${f.reason}`).join("\n")}
`,
      },
      {
        id: "available_tools",
        priority: 90,
        scope: "explorer_only",
        content: `
AVAILABLE TOOLS
---------------
${filtered.available_tools.map(t => `${t.name}: ${t.description}`).join("\n")}
`,
      },
      {
        id: "budget_status",
        priority: 40,
        scope: "explorer_only",
        content: `
BUDGET: ${filtered.remaining_budget} remaining
`,
      },
    ]
  }

  build_verifier_context(filtered: FilteredMaterial): List<ContextSection> {
    return [
      {
        id: "system_instructions",
        priority: 100,
        scope: "verifier_only",
        content: `
VERIFICATION CONTEXT
====================

GOAL: ${filtered.goal.description}
GOAL STATUS: ${filtered.goal.status}
AGGREGATE TRUST: ${filtered.aggregate_trust.toFixed(2)}

INSTRUCTION: Evaluate whether evidence is sufficient. Identify unsupported claims, contradictions, and missing evidence.
`,
      },
      {
        id: "claims_under_review",
        priority: 90,
        scope: "verifier_only",
        content: `
CLAIMS UNDER REVIEW
-------------------
${filtered.claims.map(c => `
Claim: ${c.statement}
  Trust: ${c.trust_score.toFixed(2)}
  Status: ${c.status}
  Supporting Observations (${c.supporting_observations.length}):
    ${c.supporting_observations.map(o => `- [${o.id}] ${o.tool}: ${o.summary}`).join("\n    ")}
  Supporting Claims: ${c.supporting_claims.join(", ")}
  Contradicting Claims: ${c.contradicting_claims.join(", ")}
`).join("\n")}
`,
      },
      {
        id: "contradictions",
        priority: 85,
        scope: "verifier_only",
        content: `
KNOWN CONTRADICTIONS
--------------------
${filtered.contradictions.map(c =>
  `CONFLICT: ${c.claim_a.statement} ↔ ${c.claim_b.statement}`
).join("\n")}
`,
      },
      {
        id: "evidence_gaps",
        priority: 80,
        scope: "verifier_only",
        content: `
EVIDENCE GAPS
-------------
${filtered.gaps.join("\n")}
`,
      },
    ]
  }

  build_planner_context(filtered: FilteredMaterial): List<ContextSection> {
    if (!filtered.is_incremental) {
      return [
        {
          id: "system_instructions",
          priority: 100,
          scope: "planner_only",
          content: `
INVESTIGATION PLANNING
======================

USER INTENT: ${filtered.user_intent.action} ${filtered.user_intent.target}
BUDGET: ${filtered.budget} total

INSTRUCTION: Design an Investigation Graph. Each node is an investigation task. Edges represent dependencies. Return nodes and edges.
`,
        },
        {
          id: "repository_manifest",
          priority: 90,
          scope: "planner_only",
          content: format_manifest(filtered.repository_manifest),
        },
      ]
    }

    return [
      {
        id: "system_instructions",
        priority: 100,
        scope: "planner_only",
        content: `
INCREMENTAL PLANNING UPDATE
============================

INSTRUCTION: Return only NEW nodes and edges to merge into the existing graph. Do not regenerate the full graph.
`,
      },
      {
        id: "graph_topology",
        priority: 90,
        scope: "planner_only",
        content: `
CURRENT GRAPH STATE
-------------------
Total Nodes: ${filtered.graph_summary.total}
Completed: ${filtered.graph_summary.completed}
Failed: ${filtered.graph_summary.failed}
Pending: ${filtered.graph_summary.pending}
Blocked: ${filtered.graph_summary.blocked}
`,
      },
      {
        id: "newly_discovered",
        priority: 80,
        scope: "planner_only",
        content: `
NEWLY DISCOVERED
----------------
Technologies: ${filtered.newly_discovered.technologies.join(", ")}
Files: ${filtered.newly_discovered.files.join(", ")}
Directories: ${filtered.newly_discovered.directories.join(", ")}
`,
      },
      {
        id: "verifier_feedback",
        priority: 85,
        scope: "planner_only",
        content: `
VERIFIER FEEDBACK
-----------------
${filtered.verifier_feedback.recommended_investigations.join("\n")}
`,
      },
      {
        id: "blocked_nodes",
        priority: 75,
        scope: "planner_only",
        content: `
BLOCKED NODES
-------------
${filtered.blocked_nodes.map(n =>
  `${n.id}: ${n.description} (blocked by: ${n.blocking_dependencies.join(", ")})`
).join("\n")}
`,
      },
      {
        id: "failed_nodes",
        priority: 70,
        scope: "planner_only",
        content: `
FAILED NODES
------------
${filtered.failed_nodes.map(n =>
  `${n.id}: ${n.description} (reason: ${n.failure_reason})`
).join("\n")}
`,
      },
      {
        id: "budget_status",
        priority: 40,
        scope: "planner_only",
        content: `
REMAINING BUDGET: ${filtered.remaining_budget}
`,
      },
    ]
  }
}
```

---## 10. Stage 5: Interceptor — Context Rewrite and Rejection

This stage is a strategic addition inspired by DeepSeek Harness's `agent/pre-step` event. In Wizard, it sits between the Packager and the Budget Manager.

### What It Does

After context is assembled but before it reaches the agent, the Interceptor gives registered listeners a chance to:

1. **Read** the context — inspect what will be supplied.
2. **Rewrite** the context — modify sections, add warnings, remove sensitive data.
3. **Reject** the context — block the agent call entirely (e.g., budget exhausted, security policy violation).

### Why Wizard Needs This

Wizard's investigation has runtime conditions that can change between context assembly and agent invocation:

- **Security policy** — A tool request targets a path outside the repository sandbox.
- **Budget emergency** — Remaining budget is below threshold; inject a warning or skip non-critical nodes.
- **Verifier override** — The Verifier flagged a critical contradiction; redirect the Explorer to investigate it first.
- **Duplicate detection** — The same observation was already collected; skip redundant tool calls.
- **Dynamic scoping** — New tools became available (e.g., Docker detected, so `docker_inspect` is now usable).

### Interceptor Implementation

```
Interceptor {
  listeners: List<ContextInterceptorListener> = []

  register(listener: ContextInterceptorListener): void {
    this.listeners.push(listener)
  }

  intercept(context_sections: List<ContextSection>, node: InvestigationNode, agent_type: string): InterceptorResult {
    let current_sections = context_sections
    let rejection_reason: string | null = null

    for (const listener of this.listeners) {
      if (!listener.applies_to(agent_type)) continue

      const result = listener.on_intercept(current_sections, node)

      if (result.action === "reject") {
        return {
          action: "reject",
          reason: result.reason,
          sections: current_sections,
        }
      }

      if (result.action === "rewrite") {
        current_sections = result.sections
      }
    }

    return {
      action: "proceed",
      sections: current_sections,
    }
  }
}

ContextInterceptorListener {
  name: string
  applies_to(agent_type: string): boolean
  on_intercept(sections: List<ContextSection>, node: InvestigationNode): InterceptorAction
}

InterceptorAction {
  action: "proceed" | "rewrite" | "reject"
  sections: List<ContextSection> | null   // Only for "rewrite"
  reason: string | null                    // Only for "reject"
}
```

### Built-in Interceptors

| Interceptor | Role | Agent |
|------------|------|-------|
| `SecurityPolicyInterceptor` | Blocks context if node targets paths outside sandbox | Explorer |
| `BudgetGuardInterceptor` | Injects budget warning; rejects if below critical threshold | Explorer |
| `VerifierOverrideInterceptor` | Redirects Explorer to investigate critical contradictions first | Explorer |
| `DuplicateDetectionInterceptor` | Skips nodes that would produce redundant observations | Explorer |
| `ToolAvailabilityInterceptor` | Adds newly available tools to context (e.g., Docker detected) | Explorer |

### SecurityPolicyInterceptor Example

```
SecurityPolicyInterceptor {
  applies_to(agent_type: string): boolean {
    return agent_type === "explorer"
  }

  on_intercept(sections, node): InterceptorAction {
    // Check if the node's tool targets paths outside the sandbox
    const tool = resolve_tool_for_node(node)
    const target_path = tool.parameters.path

    if (!is_within_sandbox(target_path)) {
      return {
        action: "reject",
        reason: `Tool targets path outside sandbox: ${target_path}`,
        sections: null,
      }
    }

    return {
      action: "proceed",
      sections: sections,
    }
  }
}
```

### BudgetGuardInterceptor Example

```
BudgetGuardInterceptor {
  applies_to(agent_type: string): boolean {
    return agent_type === "explorer"
  }

  on_intercept(sections, node): InterceptorAction {
    const budget = state.budget

    if (budget.remaining <= 0) {
      return {
        action: "reject",
        reason: "Investigation budget exhausted",
        sections: null,
      }
    }

    if (budget.remaining <= CRITICAL_THRESHOLD) {
      // Inject a budget warning section
      const warning_section = {
        id: "budget_warning",
        priority: 95,
        scope: "explorer_only",
        content: `
⚠️ BUDGET WARNING: Only ${budget.remaining} tool calls remaining.
Prioritize high-value investigations. Skip exploratory searches.
`,
      }
      return {
        action: "rewrite",
        sections: [...sections, warning_section],
      }
    }

    return {
      action: "proceed",
      sections: sections,
    }
  }
}
```

---## 11. Stage 6: Budget Manager — With KV Cache Optimization

The Budget Manager enforces token limits and optimizes section ordering for KV cache reuse.

### Token Budget Model

```
BudgetManager {
  max_context_tokens: number      // Total context window of the model
  reserved_for_output: number     // Always reserve 10-15% for the model's response
  system_prompt_cost: number      // Pre-computed cost of system instructions

  available_for_context(): number {
    return this.max_context_tokens
      - this.reserved_for_output
      - this.system_prompt_cost
  }

  fit(context_sections: List<ContextSection>): List<ContextSection> {
    let budget = this.available_for_context()
    let total_cost = sum_tokens(context_sections)

    if (total_cost <= budget) return context_sections

    // Progressive trimming — cut from lowest priority sections first
    let trimmed = [...context_sections].sort((a, b) => a.priority - b.priority)

    while (total_cost > budget && trimmed.length > 0) {
      const lowest = trimmed.shift()  // Remove lowest priority section
      total_cost -= lowest.token_cost
    }

    // Sort back by priority (highest first) for final ordering
    return trimmed.sort((a, b) => b.priority - a.priority)
  }
}
```

### KV Cache Optimization (Learning from DeepSeek)

DeepSeek explicitly designs for KV cache efficiency. Wizard adopts this insight: **order sections so that prefix-stable content comes first, and volatile content comes last.** This maximizes cache reuse across investigation steps.

```
KVCacheOptimizer {
  // Section stability classification
  stable_sections: Set<string> = new Set([
    "system_instructions",     // Never changes
    "available_tools",         // Stable while tool view unchanged
    "repository_summary",      // Stable across steps
  ])

  growing_sections: Set<string> = new Set([
    "verified_claims",         // Grows but appends — prefix stable
  ])

  volatile_sections: Set<string> = new Set([
    "unverified_assumptions",  // Changes frequently
    "recent_observations",     // Changes every step
    "recent_failures",         // Changes occasionally
    "budget_status",           // Changes every step
    "budget_warning",          // Appears/disappears
    "injected_context",        // Appears/disappears
  ])

  // Order sections for maximum KV cache reuse
  optimize_order(context_sections: List<ContextSection>): List<ContextSection> {
    const stable = context_sections.filter(s => this.stable_sections.has(s.id))
    const growing = context_sections.filter(s => this.growing_sections.has(s.id))
    const volatile = context_sections.filter(s => this.volatile_sections.has(s.id))

    // Within each group, maintain priority order
    stable.sort((a, b) => b.priority - a.priority)
    growing.sort((a, b) => b.priority - a.priority)
    volatile.sort((a, b) => b.priority - a.priority)

    // Stable first → growing middle → volatile last
    // This preserves KV cache hits for unchanged content across steps
    return [...stable, ...growing, ...volatile]
  }
}
```

**Why this matters:** If the first 3,000 tokens of every request are identical (system instructions, tool schemas, repository summary), the model's KV cache reuses them. Only the last 1,000 tokens (volatile observations, budget status) need recomputation. Without this ordering, every step invalidates the entire cache.

### Combined Budget + KV Cache Pipeline

```
BudgetManager {
  optimize_and_fit(context_sections: List<ContextSection>): List<ContextSection> {
    // Step 1: Order for KV cache reuse
    let ordered = this.kv_optimizer.optimize_order(context_sections)

    // Step 2: Fit within token budget (trim from lowest priority)
    let fitted = this.fit(ordered)

    return fitted
  }
}
```

---## 12. Stage 7: Context Cache and Audit

### Context Cache

Avoids redundant context construction when the same agent is called with the same node and state hasn't changed.

```
ContextCache {
  cache: Map<string, CachedContext> = new Map()
  state_version: number = 0  // Incremented on every state mutation

  get(agent_type: string, node_id: string): CachedContext | null {
    const key = `${agent_type}:${node_id}:${this.state_version}`
    return this.cache.get(key) || null
  }

  set(agent_type: string, node_id: string, context: List<ContextSection>): void {
    const key = `${agent_type}:${node_id}:${this.state_version}`
    this.cache.set(key, {
      sections: context,
      token_count: sum_tokens(context),
      timestamp: Date.now(),
    })
  }

  invalidate(): void {
    // Called when state mutates — invalidates all cached contexts
    this.state_version++
    this.cache.clear()
  }

  // Bounded cache — evict oldest entries beyond max size
  evict(max_size: number): void {
    if (this.cache.size <= max_size) return

    const entries = Array.from(this.cache.entries())
      .sort((a, b) => a[1].timestamp - b[1].timestamp)

    const to_remove = entries.slice(0, entries.length - max_size)
    for (const [key] of to_remove) {
      this.cache.delete(key)
    }
  }
}

CachedContext {
  sections: List<ContextSection>
  token_count: number
  timestamp: number
}
```

**Cache invalidation strategy:** The cache is invalidated on every state mutation. This is safe because context construction is fast (reading from in-memory stores), and correctness matters more than caching speed. The cache helps when the same node is re-evaluated without state changes (e.g., interceptor rewrite without state mutation).

### Context Audit

Records every context supplied to every agent. This is the append-only audit trail for context decisions.

```
ContextAudit {
  log: List<ContextAuditEntry> = []

  record(agent_type: string, node_id: string, context_sections: List<ContextSection>, interceptor_result: InterceptorResult): void {
    this.log.push({
      timestamp: new Date().toISOString(),
      agent: agent_type,
      node_id: node_id,
      sections_supplied: context_sections.map(s => s.id),
      total_token_count: sum_tokens(context_sections),
      interceptor_action: interceptor_result.action,
      interceptor_reason: interceptor_result.reason,
      sections_trimmed: this.log.length > 0 ?
        diff_sections(this.log[this.log.length - 1].sections_supplied, context_sections.map(s => s.id)) :
        null,
    })

    // Also append to the Investigation Event Log
    event_log.append("context_supplied", {
      agent: agent_type,
      node_id: node_id,
      sections: context_sections.map(s => s.id),
      token_count: sum_tokens(context_sections),
      interceptor_action: interceptor_result.action,
    }, { agent: "runtime" })
  }
}

ContextAuditEntry {
  timestamp: ISO8601
  agent: string
  node_id: string
  sections_supplied: List<string>
  total_token_count: number
  interceptor_action: string
  interceptor_reason: string | null
  sections_trimmed: List<string> | null
}
```

---## 14. Structured Investigation Lifecycle

The investigation runs through a structured lifecycle with clear phases and extension points. This replaces a naive linear loop with an event-driven architecture — a strategic learning from DeepSeek Harness's turn/step lifecycle.

### Lifecycle Phases

```
┌─────────────────────────────────────────────────────────────────────┐
│                    WIZARD INVESTIGATION LIFECYCLE                    │
└─────────────────────────────────────────────────────────────────────┘

PHASE 1: DISCOVERY
──────────────────
investigation/start
  → Repository Discovery (scan directory tree, detect languages, find config files)
  → event_log.append("repository_manifest", manifest)
  → state.phase = "DISCOVERY"

PHASE 2: PLANNING
─────────────────
planning/start
  → Context Engine builds Planner Context (initial, non-incremental)
  → Investigation Planner creates Investigation Graph
  → event_log.append("graph_created", { nodes, edges })
  → state.phase = "PLANNING"

planning/incremental (fires dynamically during EXECUTING)
  → Triggered by: new technology discovered, verifier recommendation, high uncertainty
  → Context Engine builds Planner Context (incremental)
  → Investigation Planner returns graph delta (new nodes + edges only)
  → event_log.append("graph_changed", delta)

PHASE 3: EXECUTING
──────────────────
executing/start
  → state.phase = "EXECUTING"
  → step_count = 0

FOR EACH EXECUTABLE NODE (topological order):
  step/start
    → event_log.append("node_started", { node_id })

    → Context Engine builds Explorer Context from state
    → Interceptor evaluates (rewrite or reject)
    → if rejected:
        event_log.append("node_skipped", { node_id, reason })
        node.status = "SKIPPED"
        continue

    → Explorer Agent receives context, returns ToolRequest
    → event_log.append("context_supplied", { agent: "explorer", node_id })

    → Tool Validation Pipeline
    → if validation failed:
        event_log.append("tool_validation_failed", { tool_request, reason })
        node.status = "FAILED"
        continue

    → Sandbox executes tool → Observation
    → event_log.append("observation", observation)

    → Claim Generator processes observation → Claims
    → for each claim:
        event_log.append("claim_created", claim)

    → Knowledge Graph updated
    → event_log.append("knowledge_updated", delta)

    → Trust Scores recomputed
    → event_log.append("claim_updated", trust_updates)

    → Budget decremented
    → event_log.append("budget_updated", state.budget)

    → node.status = "COMPLETED"
    → event_log.append("node_completed", { node_id })

  step/end
    → step_count++

    → IF step_count % verifier_interval == 0:
        verifier/assess
          → Context Engine builds Verifier Context
          → Verifier Agent evaluates evidence
          → event_log.append("verifier_assessment", assessment)
          → Context Injector injects feedback into Explorer queue

    → IF replan_trigger.should_replan(state):
        planning/incremental
          → Context Engine builds Planner Context (incremental)
          → Planner returns graph delta
          → event_log.append("graph_changed", delta)

    → Goal statuses evaluated
    → event_log.append("goal_updated", goal_updates)

PHASE 4: CONVERGENCE
────────────────────
convergence/evaluate (after every step)
  → ConvergenceEvaluator checks:
    - All goals verified?
    - Budget exhausted?
    - No executable nodes remain?
    - Contradictions unresolved?

  → If converged:
    event_log.append("investigation_converged", { reason })
    state.phase = "CONVERGED"

  → If exhausted:
    event_log.append("investigation_exhausted", { reason })
    state.phase = "EXHAUSTED"

PHASE 5: OUTPUT
───────────────
output/generate
  → Output Generator produces all artifacts from state + log:
    - Verification Report (human-readable)
    - WIZARD.md (repository memory)
    - metadata.json (machine-readable)
    - investigation_graph.json (serialized DAG)
    - knowledge_graph.json (serialized property graph)
    - claim_graph.json (serialized reasoning graph)
    - observations.json (all raw observations)
    - execution_history.json (all tool executions)
    - event_log.json (full audit trail)

output/persist
  → All artifacts written to .wizard/investigations/inv_<id>/
```

### Extension Points

The lifecycle exposes these extension points for interception and observation:

| Extension Point | Phase | Purpose |
|----------------|-------|---------|
| `investigation/start` | Discovery | Hook into repository discovery |
| `planning/start` | Planning | Observe initial graph creation |
| `planning/incremental` | Executing | Hook into dynamic graph expansion |
| `step/start` | Executing | Observe node execution start |
| `agent/pre-step` | Executing | Rewrite or reject context before agent sees it |
| `tool/validate` | Executing | Intercept tool validation |
| `tool/execute` | Executing | Intercept tool execution |
| `tool/result` | Executing | Intercept tool results before claim generation |
| `verifier/assess` | Executing | Observe verifier assessments |
| `step/end` | Executing | Observe node execution end |
| `convergence/evaluate` | Executing | Observe convergence decisions |
| `output/generate` | Output | Observe output generation |

---## 15. Complete Investigation Step Flow

This is one full investigation step showing exactly where context is built, consumed, and audited.

```
┌─────────────────────────────────────────────────────────────────────┐
│                    INVESTIGATION STEP N                              │
└─────────────────────────────────────────────────────────────────────┘

1. RUNTIME ENGINE: Identify next executable node
   → Topological sort of Investigation Graph
   → Node "verify_port_3000" is next
   → event_log.append("node_started", { node_id: "verify_port_3000" })

2. CONTEXT ENGINE — READER
   → read_current_node(state, "verify_port_3000")
   → read_claims_by_status(state, "VERIFIED").filter(relevant_to_node)
   → read_claims_by_status(state, "UNVERIFIED").filter(related_to_node)
   → read_observations_for_node(state, "verify_port_3000")
   → read_failed_executions(state, 3)
   → read_repository_summary(state)
   → read_budget(state)

3. CONTEXT ENGINE — FILTER
   → ExplorerFilter.filter(state, node)
   → Selects 5 verified claims (by trust score, relevant to node)
   → Selects 2 unverified assumptions
   → Selects 3 most recent observations
   → Selects 2 most recent failures
   → Resolves 4 available tools

4. CONTEXT ENGINE — COMPRESSOR
   → Compress observations to summaries (preserve IDs for traceability)
   → Compress claims to structured summaries (preserve provenance)
   → Aggregate repository knowledge to overview
   → Format failures concisely

5. CONTEXT ENGINE — PACKAGER
   → build_explorer_context(filtered)
   → Assembles modular sections:
     - system_instructions (priority 100)
     - available_tools (priority 90)
     - repository_summary (priority 80)
     - verified_claims (priority 75)
     - unverified_assumptions (priority 70)
     - recent_observations (priority 60)
     - recent_failures (priority 50)
     - budget_status (priority 40)

6. CONTEXT ENGINE — INTERCEPTOR
   → SecurityPolicyInterceptor: passes (port check is within sandbox)
   → BudgetGuardInterceptor: passes (budget above critical threshold)
   → VerifierOverrideInterceptor: no override needed
   → Result: proceed with original context

7. CONTEXT ENGINE — BUDGET MANAGER
   → KV Cache Optimizer orders sections:
     Stable: system_instructions, available_tools, repository_summary
     Growing: verified_claims
     Volatile: unverified_assumptions, recent_observations, recent_failures, budget_status
   → Token count: 3,200
   → Budget available: 4,000
   → Fits — no trimming needed

8. CONTEXT ENGINE — CACHE
   → Cache miss (new node, state changed since last step)
   → Context constructed fresh

9. CONTEXT ENGINE — AUDIT
   → Records: agent=explorer, node=verify_port_3000, sections=[...], tokens=3200
   → Appends to event_log: "context_supplied"

10. EXPLORER AGENT receives context
    → Returns: { tool: "check_port", parameters: { port: 3000 }, reasoning: "..." }

11. RUNTIME ENGINE validates ToolRequest
    → Schema valid, parameters correct, within budget, not duplicate
    → event_log.append("tool_validated", { tool_request })

12. SANDBOX executes tool
    → Observation created: OBS-61 "Port 3000 accepting connections"
    → event_log.append("observation", OBS-61)

13. CLAIM GENERATOR processes observation
    → New claim: "Application reachable on port 3000" (trust: 0.85)
    → event_log.append("claim_created", claim)

14. KNOWLEDGE GRAPH updated
    → New node: "Port 3000"
    → New edge: "Application" → "LISTENS_ON" → "Port 3000"
    → event_log.append("knowledge_updated", delta)

15. TRUST SCORES recomputed
    → "Runtime Verified" claim: 0.85 → 0.92
    → event_log.append("claim_updated", trust_updates)

16. BUDGET decremented
    → event_log.append("budget_updated", state.budget)

17. NODE marked COMPLETED
    → event_log.append("node_completed", { node_id: "verify_port_3000" })

18. VERIFIER CALLED (every 5 steps, if step_count % 5 == 0)
    → Context Engine builds Verifier Context (different structure)
    → Verifier returns: "Evidence sufficient for runtime goal"
    → event_log.append("verifier_assessment", assessment)
    → Context Injector injects feedback into Explorer queue

19. DYNAMIC GRAPH EXPANSION (if replan_trigger fires)
    → Context Engine builds Planner Context (incremental)
    → Planner returns graph delta
    → event_log.append("graph_changed", delta)

20. GOAL EVALUATION
    → "Verify Runtime" goal: trust 0.92, status PARTIAL → VERIFIED
    → event_log.append("goal_updated", { goal_id, status: "VERIFIED" })

21. RUNTIME INVARIANT CHECK
    → deriveInvestigationState(event_log) reconstructs state
    → assert(reconstructed == current_state)
    → Pass

22. CONVERGENCE EVALUATION
    → All goals verified? Yes
    → Investigation complete
    → event_log.append("investigation_converged", { reason: "all_goals_verified" })
```

---## 16. Evidence Chain & Traceability

Every conclusion in the final report is traceable back through the full evidence chain to the original tool execution and user intent.

### Traceability Path

```
Report Conclusion
  → Claim (with trust score and status)
    → Provenance (derived_from_observations, derived_from_claims)
      → Observations (with tool, parameters, raw_output, timestamp)
        → ToolExecution (with validation result, sandbox output)
          → InvestigationNode (with hypothesis, dependencies)
            → InvestigationGraph (with edges showing investigation path)
              → User Intent (original action and target)
```

### EvidenceChain Object

```
EvidenceChain {
  conclusion: string              // "Runtime = Node.js"
  claim_id: string                // "CLM-15"
  trust_score: number             // 0.92
  chain: List<EvidenceStep>       // Ordered steps from observation to conclusion

  // Traceability metadata
  observation_ids: List<string>   // All observations supporting this conclusion
  tool_execution_ids: List<string> // All tool executions that produced these observations
  node_ids: List<string>          // All investigation nodes involved
  goal_id: string                 // Which goal this conclusion satisfies
  intent: { action, target }      // Original user intent
}

EvidenceStep {
  step_number: number
  type: "observation" | "claim" | "knowledge_update"
  id: string                      // Observation ID, Claim ID, or Knowledge Node ID
  description: string             // Human-readable description of this step
  timestamp: ISO8601
  provenance: {
    derived_from: List<string>    // IDs of previous steps this step depends on
  }
}
```

### Building Evidence Chains

```
EvidenceChainBuilder {
  build_chain(claim_id: string): EvidenceChain {
    const claim = state.claim_graph.get_node(claim_id)
    const chain = []
    const visited = new Set()

    // Walk backwards from claim to observations
    this.walk_backwards(claim, chain, visited)

    // Sort by timestamp
    chain.sort((a, b) => a.timestamp - b.timestamp)

    // Number the steps
    chain.forEach((step, i) => step.step_number = i + 1)

    return {
      conclusion: claim.statement,
      claim_id: claim.id,
      trust_score: claim.trust_score,
      chain: chain,
      observation_ids: collect_observation_ids(chain),
      tool_execution_ids: collect_execution_ids(chain),
      node_ids: collect_node_ids(chain),
      goal_id: resolve_goal_for_claim(claim_id),
      intent: state.intent,
    }
  }

  walk_backwards(item, chain, visited): void {
    if (visited.has(item.id)) return
    visited.add(item.id)

    chain.push({
      type: item.type,
      id: item.id,
      description: item.description,
      timestamp: item.timestamp,
      provenance: item.provenance,
    })

    // Recurse into provenance
    for (const parent_id of item.provenance.derived_from) {
      const parent = resolve_item(parent_id)
      this.walk_backwards(parent, chain, visited)
    }
  }
}
```

---## 17. Trust Score Computation

Trust scores are computed by deterministic algorithms in the Runtime Engine, never by the LLM. This is a core principle: **confidence ≠ evidence**.

### Trust Score Formula

```
TrustScoreComputer {
  compute(claim: Claim): number {
    const observation_weight = this.compute_observation_weight(claim)
    const execution_bonus = this.compute_execution_bonus(claim)
    const support_bonus = this.compute_support_bonus(claim)
    const contradiction_penalty = this.compute_contradiction_penalty(claim)
    const recency_factor = this.compute_recency_factor(claim)

    const raw_score = (observation_weight + execution_bonus + support_bonus)
                      - contradiction_penalty
                      * recency_factor

    return clamp(raw_score, 0.0, 1.0)
  }

  compute_observation_weight(claim: Claim): number {
    const observations = claim.provenance.derived_from_observations
    if (observations.length === 0) return 0.0

    // Each observation contributes based on its tool type
    const tool_weights = {
      execute_command: 0.3,    // Execution evidence is strong
      check_port: 0.25,         // Network evidence is strong
      read_file: 0.2,           // File evidence is moderate
      search_repository: 0.15,  // Search evidence is weaker
    }

    let weight = 0.0
    for (const obs_id of observations) {
      const obs = state.observations.get(obs_id)
      weight += (tool_weights[obs.tool] || 0.1) * (obs.success ? 1.0 : 0.0)
    }

    return min(weight, 0.6)  // Cap observation weight at 0.6
  }

  compute_execution_bonus(claim: Claim): number {
    // Bonus if the claim is supported by successful execution
    const execution_obs = claim.provenance.derived_from_observations
      .map(id => state.observations.get(id))
      .filter(o => o.tool === "execute_command" && o.success)

    return execution_obs.length * 0.1  // 0.1 per successful execution
  }

  compute_support_bonus(claim: Claim): number {
    // Bonus from supporting claims (with diminishing returns)
    const supporting = claim.supporting_claims
      .map(id => state.claim_graph.get_node(id))
      .filter(c => c.status === "VERIFIED")

    if (supporting.length === 0) return 0.0

    // Diminishing returns: first supporter = 0.15, second = 0.10, third+ = 0.05 each
    let bonus = 0.0
    for (let i = 0; i < supporting.length; i++) {
      if (i === 0) bonus += 0.15
      else if (i === 1) bonus += 0.10
      else bonus += 0.05
    }

    return min(bonus, 0.3)  // Cap support bonus at 0.3
  }

  compute_contradiction_penalty(claim: Claim): number {
    // Penalty from contradicting claims
    const contradicting = claim.contradicting_claims
      .map(id => state.claim_graph.get_node(id))
      .filter(c => c.status !== "CONTRADICTED")

    if (contradicting.length === 0) return 0.0

    // Weight by the trust score of contradicting claims
    let penalty = 0.0
    for (const c of contradicting) {
      penalty += c.trust_score * 0.2  // Higher trust contradiction = higher penalty
    }

    return min(penalty, 0.5)  // Cap penalty at 0.5
  }

  compute_recency_factor(claim: Claim): number {
    // Slight decay for very old claims without recent evidence
    const last_updated = claim.last_updated
    const age_hours = (Date.now() - last_updated) / (1000 * 60 * 60)

    if (age_hours < 1) return 1.0       // Fresh
    if (age_hours < 24) return 0.95     // Less than a day
    if (age_hours < 168) return 0.9     // Less than a week
    return 0.85                         // Older
  }
}
```

### Trust Score to Claim Status Mapping

| Trust Score Range | Claim Status |
|-------------------|-------------|
| 0.80 - 1.00 | VERIFIED |
| 0.50 - 0.79 | PARTIAL |
| 0.20 - 0.49 | UNVERIFIED |
| 0.00 - 0.19 | CONTRADICTED |

---## 18. Runtime Invariant Enforcement

After every state mutation, the Runtime Engine verifies that the current state is reconstructable from the event log. This is the automated guarantee of traceability.

### Invariant Checks

```
RuntimeInvariant {
  verify(event_log: InvestigationEventLog, current_state: InvestigationState): boolean {
    // Reconstruct state from log
    const reconstructed = deriveInvestigationState(event_log)

    // Check 1: All observations in state exist in log
    for (const [id, obs] of current_state.observations) {
      const log_event = event_log.find(e =>
        e.type === "observation" && e.data.id === id
      )
      if (!log_event) {
        throw new InvariantViolation(
          `Observation ${id} exists in state but not in event log`
        )
      }
    }

    // Check 2: All claims in state exist in log
    for (const claim of current_state.claim_graph.nodes) {
      const log_event = event_log.find(e =>
        e.type === "claim_created" && e.data.id === claim.id
      )
      if (!log_event) {
        throw new InvariantViolation(
          `Claim ${claim.id} exists in state but not in event log`
        )
      }
    }

    // Check 3: All investigation graph nodes exist in log
    for (const node of current_state.investigation_graph.nodes) {
      const log_event = event_log.find(e =>
        (e.type === "graph_created" || e.type === "graph_changed") &&
        e.data.nodes && e.data.nodes.some(n => n.id === node.id)
      )
      if (!log_event) {
        throw new InvariantViolation(
          `Graph node ${node.id} exists in state but not in event log`
        )
      }
    }

    // Check 4: Budget is consistent
    const budget_events = event_log.filter(e => e.type === "budget_updated")
    if (budget_events.length === 0) {
      throw new InvariantViolation("No budget events in event log")
    }
    const last_budget = budget_events[budget_events.length - 1].data
    if (last_budget.remaining !== current_state.budget.remaining) {
      throw new InvariantViolation(
        `Budget mismatch: log=${last_budget.remaining}, state=${current_state.budget.remaining}`
      )
    }

    // Check 5: Phase is consistent
    const phase_events = event_log.filter(e => e.type === "phase_changed")
    if (phase_events.length > 0) {
      const last_phase = phase_events[phase_events.length - 1].data.phase
      if (last_phase !== current_state.phase) {
        throw new InvariantViolation(
          `Phase mismatch: log=${last_phase}, state=${current_state.phase}`
        )
      }
    }

    // Check 6: All provenance references resolve
    for (const claim of current_state.claim_graph.nodes) {
      for (const obs_id of claim.provenance.derived_from_observations) {
        if (!current_state.observations.has(obs_id)) {
          throw new InvariantViolation(
            `Claim ${claim.id} references non-existent observation ${obs_id}`
          )
        }
      }
    }

    return true
  }
}
```

### When Invariants Are Checked

| Trigger | Frequency |
|---------|-----------|
| After every observation appended | Every tool execution |
| After every claim created | Every claim generation |
| After every graph change | Every planning update |
| After every verifier round | Every N steps |
| Before convergence | Once at end |
| On demand | Via `runtime_invariant.verify()` call |

---## 19. Context Injection — Async Context Updates

Context Injection allows components to push context into the next agent step without rebuilding everything. This is a strategic learning from DeepSeek Harness's `agent.inject()`.

### How It Works

```
ContextInjector {
  queue: List<ContextInjection> = []

  // Any component can inject context for a future agent call
  inject(section: ContextSection, target_agent: string, injected_by: string): void {
    const injection = {
      id: generate_id(),
      section: section,
      target_agent: target_agent,
      injected_by: injected_by,
      timestamp: new Date().toISOString(),
      consumed: false,
    }

    this.queue.push(injection)
    state.context_injection_queue.push(injection)

    // Record in event log
    event_log.append("context_injected", {
      injection_id: injection.id,
      section_id: section.id,
      target_agent: target_agent,
      injected_by: injected_by,
    }, { agent: injected_by })
  }

  // Called by Context Engine during context construction
  drain(target_agent: string): List<ContextSection> {
    const injections = this.queue
      .filter(i => i.target_agent === target_agent && !i.consumed)
      .sort((a, b) => a.timestamp.localeCompare(b.timestamp))

    // Mark as consumed
    for (const injection of injections) {
      injection.consumed = true
    }

    // Remove consumed injections from queue
    this.queue = this.queue.filter(i => !i.consumed)

    return injections.map(i => i.section)
  }
}
```

### Use Cases

| Injector | Target | Section Injected | Trigger |
|----------|--------|-----------------|---------|
| Verifier | Explorer | `verifier_feedback` — "Investigate contradiction between Claim A and Claim B" | After verifier round |
| Planner | Explorer | `graph_update` — "New investigation nodes available: X, Y, Z" | After incremental planning |
| Runtime Engine | Explorer | `budget_warning` — "Only N tool calls remaining" | When budget below threshold |
| Runtime Engine | Explorer | `tool_available` — "New tool detected: docker_inspect" | When new technology discovered |
| Runtime Engine | Verifier | `new_evidence` — "New observation relevant to goal G" | After high-impact observation |

### Integration with Context Engine

During context construction (Stage 4: Packager), injected sections are merged:

```
Packager {
  build_explorer_context(filtered, injector): List<ContextSection> {
    // Build base sections
    let sections = this.build_base_explorer_sections(filtered)

    // Drain injected context
    const injected = injector.drain("explorer")
    sections = [...sections, ...injected]

    return sections
  }
}
```

Injected sections carry their own priority and are ordered by the Budget Manager alongside base sections.

---## 20. Investigation Fork and Resume

Forking creates an alternative investigation path from any point in the event log. Resuming continues an interrupted investigation from a serialized checkpoint.

### Fork

```
InvestigationForker {
  // Fork from a specific log boundary
  fork(event_log: InvestigationEventLog, boundary_seq: number, new_investigation_id: UUID): ForkedInvestigation {
    // Take all events up to and including the boundary
    const forked_events = event_log.events.filter(e => e.seq <= boundary_seq)

    // Reconstruct state from forked log
    const state = deriveInvestigationState(forked_events)

    // Create new log with forked prefix
    const new_log = new InvestigationEventLog()
    new_log.events = forked_events
    new_log.seq_counter = boundary_seq

    // Update investigation ID in new state
    state.investigation_id = new_investigation_id

    return {
      investigation_id: new_investigation_id,
      event_log: new_log,
      state: state,
      fork_point: boundary_seq,
      parent_investigation_id: state.intent.original_investigation_id,
    }
  }
}

ForkedInvestigation {
  investigation_id: UUID
  event_log: InvestigationEventLog
  state: InvestigationState
  fork_point: number          // Sequence number where fork occurred
  parent_investigation_id: UUID | null
}
```

### Resume

```
InvestigationResumer {
  // Resume from a serialized investigation
  resume(serialized_path: string): ResumedInvestigation {
    // Load all serialized artifacts
    const log = load_json(`${serialized_path}/event_log.json`)
    const state = load_json(`${serialized_path}/investigation_state.json`)

    // Reconstruct from log (authoritative)
    const reconstructed_state = deriveInvestigationState(log)

    // Verify consistency
    assert(reconstructed_state.is_consistent())

    return {
      investigation_id: reconstructed_state.investigation_id,
      event_log: log,
      state: reconstructed_state,
      resume_point: log.events.length,
    }
  }
}
```

### Use Cases

| Scenario | How |
|----------|-----|
| Explore alternative investigation paths | Fork at a decision point, run two strategies in parallel |
| Resume interrupted investigation | Resume from last serialized checkpoint |
| Compare investigation strategies | Fork at same point, apply different planner configs |
| Replay for debugging | Resume from any checkpoint, step through manually |
| Continue after budget exhaustion | Fork at a high-value point, increase budget, continue |

---## 21. Persistence & Serialization

When the investigation completes (or at periodic checkpoints), the entire investigation state is serialized to disk.

### Output Directory Structure

```
.wizard/
└── investigations/
    └── inv_<timestamp>/
        ├── investigation_state.json    // Full InvestigationState snapshot
        ├── event_log.json              // Complete append-only event log
        ├── investigation_graph.json    // Serialized DAG
        ├── knowledge_graph.json        // Serialized property graph
        ├── claim_graph.json            // Serialized reasoning graph
        ├── observations.json           // All raw observations
        ├── execution_history.json      // All tool executions
        ├── report.md                   // Human-readable verification report
        ├── wizard.md                   // Repository memory document
        ├── metadata.json               // Machine-readable metadata
        ├── context_audit.json          // Context supply audit trail
        └── evidence_chains/            // Per-claim evidence chains
            ├── CLM-01.json
            ├── CLM-02.json
            └── ...
```

### Serialization

```
PersistenceManager {
  persist(state: InvestigationState, event_log: InvestigationEventLog, output_dir: string): void {
    const timestamp = generate_id()
    const inv_dir = `${output_dir}/.wizard/investigations/inv_${timestamp}`

    create_directory(inv_dir)

    // Core state
    write_json(`${inv_dir}/investigation_state.json`, state)
    write_json(`${inv_dir}/event_log.json`, event_log.events)

    // Graphs
    write_json(`${inv_dir}/investigation_graph.json`, serialize_dag(state.investigation_graph))
    write_json(`${inv_dir}/knowledge_graph.json`, serialize_graph(state.knowledge_graph))
    write_json(`${inv_dir}/claim_graph.json`, serialize_graph(state.claim_graph))

    // Stores
    write_json(`${inv_dir}/observations.json`, Array.from(state.observations.values()))
    write_json(`${inv_dir}/execution_history.json`, state.execution_history)

    // Human-readable outputs
    write_markdown(`${inv_dir}/report.md`, generate_report(state, event_log))
    write_markdown(`${inv_dir}/wizard.md`, generate_wizard_md(state, event_log))
    write_json(`${inv_dir}/metadata.json`, generate_metadata(state, event_log))

    // Audit
    write_json(`${inv_dir}/context_audit.json`, context_audit.log)

    // Evidence chains
    const chains_dir = `${inv_dir}/evidence_chains`
    create_directory(chains_dir)
    for (const claim of state.claim_graph.nodes) {
      const chain = evidence_chain_builder.build_chain(claim.id)
      write_json(`${chains_dir}/${claim.id}.json`, chain)
    }
  }
}
```

---## 22. API Surface — Class Reference

### ContextEngine (Main Orchestrator)

```
class ContextEngine {
  // Components
  reader: Reader
  filters: Map<string, Filter>          // "explorer" → ExplorerFilter, etc.
  compressor: Compressor
  packager: Packager
  interceptor: Interceptor
  budget_manager: BudgetManager
  cache: ContextCache
  audit: ContextAudit
  injector: ContextInjector
  section_registry: ContextSectionRegistry

  // Main entry point
  build_context(
    state: InvestigationState,
    agent_type: "explorer" | "verifier" | "planner",
    node: InvestigationNode | null,
    is_incremental: boolean = false
  ): ContextBuildResult {
    // 1. Check cache
    const cache_key = `${agent_type}:${node?.id}:${state.version}`
    const cached = this.cache.get(agent_type, node?.id || "global")
    if (cached) return { sections: cached.sections, from_cache: true }

    // 2. Read from state
    const filter = this.filters.get(agent_type)
    const filtered = filter.filter(state, node, is_incremental)

    // 3. Compress
    const compressed = this.compressor.compress(filtered)

    // 4. Package into modular sections
    let sections = this.packager.build_sections(compressed, agent_type)

    // 5. Add injected context
    const injected = this.injector.drain(agent_type)
    sections = [...sections, ...injected]

    // 6. Interceptor (rewrite or reject)
    const intercept_result = this.interceptor.intercept(sections, node, agent_type)
    if (intercept_result.action === "reject") {
      return { sections: [], rejected: true, reason: intercept_result.reason }
    }
    if (intercept_result.action === "rewrite") {
      sections = intercept_result.sections
    }

    // 7. Budget + KV cache optimization
    sections = this.budget_manager.optimize_and_fit(sections)

    // 8. Cache
    this.cache.set(agent_type, node?.id || "global", sections)

    // 9. Audit
    this.audit.record(agent_type, node?.id || "global", sections, intercept_result)

    return { sections, from_cache: false }
  }

  // Lifecycle
  on_state_mutation(): void {
    this.cache.invalidate()
  }
}

ContextBuildResult {
  sections: List<ContextSection>
  from_cache: boolean
  rejected: boolean
  reason: string | null
}
```

### UnifiedInvestigationLog

```
class UnifiedInvestigationLog {
  events: InvestigationEvent[] = []
  seq_counter: number = 0
  listeners: Map<string, Function[]> = new Map()

  append(event_type: string, data: any, provenance?: Provenance): InvestigationEvent {
    const event = {
      type: event_type,
      seq: ++this.seq_counter,
      timestamp: new Date().toISOString(),
      investigation_id: data.investigation_id,
      node_id: data.node_id || null,
      goal_id: data.goal_id || null,
      data: data,
      provenance: provenance || {},
    }

    this.events.push(event)
    this.notify(event_type, event)

    return event
  }

  derive_state(): InvestigationState {
    return deriveInvestigationState(this.events)
  }

  fork(at_seq: number, new_id: UUID): UnifiedInvestigationLog {
    const forked_events = this.events.filter(e => e.seq <= at_seq)
    const new_log = new UnifiedInvestigationLog()
    new_log.events = forked_events
    new_log.seq_counter = at_seq
    return new_log
  }

  subscribe(event_type: string, callback: Function): void {
    if (!this.listeners.has(event_type)) {
      this.listeners.set(event_type, [])
    }
    this.listeners.get(event_type).push(callback)
  }

  notify(event_type: string, event: InvestigationEvent): void {
    const callbacks = this.listeners.get(event_type) || []
    for (const cb of callbacks) {
      cb(event)
    }
  }
}
```

---## 23. Design Decisions & Tradeoffs

### Decision 1: Stores AND Log (Not Log-Only)

| Aspect | Choice | Reasoning |
|--------|--------|-----------|
| Context construction reads from | Stores (fast random access) | Scanning a 500-event log on every step is wasteful when stores are already in memory |
| Audit and reconstruction uses | Log (authoritative record) | The log is the ground truth for traceability, fork, and resume |
| Consistency guaranteed by | Runtime invariant | After every mutation, `deriveInvestigationState(log) == current_state` |

**Tradeoff:** Slight complexity of maintaining two representations. Worth it because stores give O(1) queries during context construction, while the log gives O(n) reconstruction only when needed (fork, resume, audit, invariant check).

### Decision 2: Modular Sections (Not Monolithic Templates)

| Aspect | Choice | Reasoning |
|--------|--------|-----------|
| Context templates | Modular, registered sections | New sections can be added without modifying core code |
| Section scope | Per-agent (explorer, verifier, planner) | Each agent gets exactly what it needs |
| Section priority | Numeric, higher = trimmed last | Budget Manager trims by priority, not hardcoded order |

**Tradeoff:** Slightly more complex assembly logic. Worth it because it makes the system extensible and enables KV cache optimization through stable section ordering.

### Decision 3: Interceptor Stage (Not Direct Agent Invocation)

| Aspect | Choice | Reasoning |
|--------|--------|-----------|
| Context validation | Interceptor stage between Packager and Budget Manager | Allows runtime conditions to modify or block context |
| Interceptor actions | Proceed, rewrite, reject | Covers all cases: normal flow, modification, and blocking |
| Built-in interceptors | Security, budget, verifier override, duplicate detection | Common runtime concerns handled automatically |

**Tradeoff:** Extra pipeline stage adds latency. Worth it because it enables security policy enforcement, budget guards, and verifier overrides without modifying the agent loop.

### Decision 4: KV Cache Optimization (Not Naive Ordering)

| Aspect | Choice | Reasoning |
|--------|--------|-----------|
| Section ordering | Stable first, growing middle, volatile last | Maximizes KV cache reuse across steps |
| Stable sections | System instructions, tool schemas, repository summary | Never change during investigation |
| Volatile sections | Recent observations, budget status, injected context | Change every step |

**Tradeoff:** Slightly different section ordering than pure priority sort. Worth it because it can reduce token processing cost by 50-70% through cache reuse.

### Decision 5: Deterministic Trust Scores (Not LLM-Computed)

| Aspect | Choice | Reasoning |
|--------|--------|-----------|
| Trust computation | Deterministic algorithm in Runtime Engine | Confidence ≠ evidence; LLMs can be 99% confident and wrong |
| Formula components | Observation weight, execution bonus, support bonus, contradiction penalty, recency factor | Evidence-based, not opinion-based |
| Status mapping | Score ranges map to VERIFIED/PARTIAL/UNVERIFIED/CONTRADICTED | Clear thresholds, no ambiguity |

**Tradeoff:** Less nuanced than LLM judgment. Worth it because it's reproducible, auditable, and immune to LLM hallucination.

### Decision 6: Stateless Agents (Not Persistent Agent Memory)

| Aspect | Choice | Reasoning |
|--------|--------|-----------|
| Agent memory | None — stateless | Determinism, no cross-contamination, reproducibility |
| State ownership | Runtime Engine exclusively | Single source of truth |
| Context supply | Fresh construction from state on every call | Always reflects current state |

**Tradeoff:** Cannot leverage agent memory for optimization. Worth it because it eliminates state drift, makes debugging trivial, and ensures every decision is based on current evidence.

---## 24. Viva-Ready Defense

### Q1: How do the agents hold context?

**Answer:** They don't. The agents are stateless. The Runtime Engine owns all state. The Context Engine constructs fresh context from state on every agent call. The agent receives context, returns a decision, and forgets everything. This is by design — it ensures determinism, eliminates cross-contamination, and makes every decision reproducible.

### Q2: What context does the Explorer Agent receive?

**Answer:** The Explorer receives exactly what it needs to answer "what is the highest-value next action?" — the current goal, verified knowledge (with evidence links), unverified assumptions (labeled as such), recent observations, recent failures, available tools, budget status, and repository overview. It does NOT receive all observations, all claims, or the full knowledge graph. We intentionally minimize context to reduce latency and token cost while preserving discriminative power.

### Q3: What context does the Verifier Agent receive?

**Answer:** The Verifier receives a different context — claims under review with their full provenance (supporting observations, supporting claims, contradicting claims), known contradictions, evidence gaps, and aggregate trust scores. It does NOT receive tool definitions or repository structure. Its job is to evaluate evidence, not to decide what to investigate next.

### Q4: What context does the Planner Agent receive?

**Answer:** The Planner receives either the full repository manifest (initial planning) or an incremental update (graph topology, newly discovered technologies, verifier feedback, blocked/failed nodes, remaining goals, remaining budget). It does NOT receive raw observations or individual claims. Its job is to design investigation structure, not to evaluate evidence.

### Q5: Why not just dump everything into one giant context?

**Answer:** Three reasons:
1. **Token budget** — the model's context window is finite. Dumping everything wastes budget on irrelevant data.
2. **Signal-to-noise** — too much context degrades reasoning. The agent needs focused information for its specific role.
3. **Causal history** — naive compression destroys the reasoning trail. Our compressor shrinks payloads while preserving provenance links, so every conclusion remains traceable.

### Q6: How do you trace a conclusion backwards?

**Answer:** Every claim carries provenance — `derived_from_observations` and `derived_from_claims`. Follow the chain: claim → observations → tool executions → investigation nodes → investigation graph → user intent. The `EvidenceChainBuilder` automates this. The final report includes evidence chains for every conclusion. The event log provides the full audit trail.

### Q7: What is the Investigation Event Log and why does it exist?

**Answer:** The Investigation Event Log is an append-only event stream that records every mutation to the investigation — observations, claims, graph changes, verifier assessments, budget updates. It serves three purposes: (1) audit trail — every change is recorded with sequence number, timestamp, and provenance; (2) reconstructability — the entire state can be reconstructed from the log via `deriveInvestigationState()`; (3) fork and resume — fork the log at any sequence number to create an alternative investigation path.

### Q8: Why both stores AND a log? Doesn't that duplicate data?

**Answer:** The stores exist for fast random-access queries during context construction. The Reader reads from stores, not from the log — scanning a 500-event log on every step is wasteful when the stores are already in memory. The log exists for audit, reconstruction, fork, and resume. The runtime invariant ensures they stay consistent. This is a performance tradeoff: slight duplication for O(1) queries during the hot path, with O(n) reconstruction only when needed.

### Q9: How does compression preserve causal history?

**Answer:** Four rules: (1) Compress the payload, not the provenance — observation IDs, tool names, and paths are always preserved; (2) Preserve the causal chain — `EvidenceChain` objects carry the full step history from observation to conclusion; (3) Compress by aggregation, not deletion — old observations are aggregated with counts and key highlights, not dropped; (4) Compress by evidential weight — execution output is compressed minimally, search results are compressed aggressively.

### Q10: What is the Interceptor and why does it exist?

**Answer:** The Interceptor sits between the Packager and the Budget Manager. After context is assembled but before it reaches the agent, registered listeners can read, rewrite, or reject the context. This enables runtime conditions to modify what the agent sees — security policy enforcement, budget guards, verifier overrides, duplicate detection, and dynamic tool availability — without modifying the agent loop.

### Q11: How does KV cache optimization work?

**Answer:** Sections are ordered so that prefix-stable content comes first (system instructions, tool schemas, repository summary) and volatile content comes last (recent observations, budget status, injected context). This means the first 3,000 tokens of every request are identical across steps, so the model's KV cache reuses them. Only the last 1,000 tokens need recomputation. Without this ordering, every step invalidates the entire cache.

### Q12: What is Context Injection?

**Answer:** Context Injection allows components to push context into the next agent step without rebuilding everything. The Verifier can inject feedback after a verification round. The Planner can inject graph updates after incremental planning. The Runtime Engine can inject budget warnings when running low. Injected sections are drained during context construction and merged with base sections.

### Q13: How do trust scores work?

**Answer:** Trust scores are computed by a deterministic algorithm in the Runtime Engine, never by the LLM. The formula considers: observation weight (based on tool type and success), execution bonus (successful command execution), support bonus (verified supporting claims, with diminishing returns), contradiction penalty (contradicting claims, weighted by their trust), and recency factor (slight decay for old claims). Scores map to statuses: VERIFIED (0.80+), PARTIAL (0.50-0.79), UNVERIFIED (0.20-0.49), CONTRADICTED (0.00-0.19).

### Q14: What is the Runtime Invariant?

**Answer:** After every state mutation, the Runtime Engine verifies that the current state is reconstructable from the event log. It checks: all observations in state exist in the log, all claims in state exist in the log, all graph nodes in state exist in the log, budget is consistent, phase is consistent, and all provenance references resolve. If any check fails, an `InvariantViolation` is thrown. This is the automated guarantee of traceability.

### Q15: How does fork and resume work?

**Answer:** Forking takes all events up to a boundary sequence number, reconstructs state from them, and creates a new investigation with a forked log prefix. Resuming loads a serialized investigation, reconstructs state from the event log, and verifies consistency. This enables exploring alternative investigation paths, resuming interrupted investigations, comparing strategies, and replaying for debugging.

### Q16: What learnings came from DeepSeek Harness and how were they applied?

**Answer:** Five strategic learnings were applied without copying DeepSeek's architecture:

1. **Append-only event log as audit backbone** — Wizard adds the Investigation Event Log alongside its existing stores, getting reconstructability and fork/resume without sacrificing query speed.

2. **Modular context sections** — Wizard replaces monolithic templates with registered sections, making context extensible without modifying core code.

3. **Interceptor stage** — Inspired by DeepSeek's `agent/pre-step`, Wizard adds an Interceptor stage between Packager and Budget Manager for runtime context validation.

4. **KV cache optimization** — Inspired by DeepSeek's explicit KV cache design, Wizard orders sections for prefix stability, reducing token processing cost by 50-70%.

5. **Context injection** — Inspired by DeepSeek's `agent.inject()`, Wizard adds async context injection for verifier feedback, planner updates, and budget warnings.

Wizard does NOT copy DeepSeek's plugin architecture, Cordis framework, or session fork model. Wizard keeps its own three-graph model, evidence-based trust scores, stateless agents, and structured investigation lifecycle. The learnings are applied as enhancements, not replacements.

---

## Summary: What This Architecture Achieves

| Capability | How |
|-----------|-----|
| **Discriminative context** | Seven-stage pipeline reads, filters, compresses, packages, intercepts, budgets, and audits |
| **Causal traceability** | Provenance links in every summary, EvidenceChain objects, append-only event log |
| **Agent specialization** | Three different context structures for Explorer, Verifier, and Planner |
| **Budget efficiency** | Progressive trimming by priority, KV cache optimization, context caching |
| **Runtime safety** | Interceptor stage for security policy, budget guards, and verifier overrides |
| **Reproducibility** | Runtime invariant enforcement, deterministic trust scores, stateless agents |
| **Extensibility** | Modular context sections, interceptor listeners, context injection |
| **Fork and resume** | Event log reconstruction, fork at any boundary, resume from checkpoint |
| **Audit trail** | Event log records every mutation, context audit records every context supply |

---

| **Foundational Principles** | Seven distinctions separating this from naive context management |
| **Investigation State** | Single source of truth for random-access queries |
| **Investigation Event Log** | Append-only audit trail for reconstructability and fork/resume |
| **Seven-Stage Context Engine** | Reader → Filter → Compressor → Packager → Interceptor → Budget Manager → Cache + Audit |
| **Modular Context Sections** | Registered, scoped, prioritized — not monolithic templates |
| **Interceptor Stage** | Runtime validation, rewrite, and rejection before agent sees context |
| **KV Cache Optimization** | Prefix-stable section ordering for 50-70% token processing savings |
| **Context Injection** | Async context updates from Verifier, Planner, and Runtime Engine |
| **Structured Lifecycle** | Event-driven phases with extension points at every stage |
| **Evidence Chains** | Full traceability from report conclusion to original user intent |
| **Deterministic Trust Scores** | Evidence-based, algorithmic, immune to LLM hallucination |
| **Runtime Invariants** | Automated traceability enforcement after every mutation |
| **Fork and Resume** | Alternative investigation paths, checkpoint recovery, strategy comparison |

This is the Wizard Context Engine — a seven-stage projection system that transforms investigation state into focused, budget-aware, traceable context for each reasoning component, preserving the evidence trail at every stage.