# Runtime Integration

This subsystem does **not** implement the Runtime Engine. This document
specifies exactly what the Runtime Engine developer needs to build
against to integrate without modifying agent code.

## Integration flow

```
Investigation Planner / Runtime
        |
        v
   ExplorerInput            <-- Runtime/Planner constructs this
        |
        v
   ExplorerAgent.investigate()   (or POST /explorer/investigate)
        |
        v
   ExplorerOutput            <-- validated Tool Request / Execution Plan
        |
        v
   Runtime executes the ToolRequest      <-- Runtime's own responsibility
        |
        v
   Observation                <-- Runtime-owned type, not defined by this subsystem
        |
        v
   Runtime updates its Claims Graph
        |
        v
   VerificationInput          <-- Runtime constructs this from the Claims Graph
        |
        v
   VerificationAgent.verify()   (or POST /verification/verify)
        |
        v
   VerificationOutput          <-- structured assessment + report_markdown
        |
        v
   Runtime writes verification_report.md
```

## What Runtime must provide to Explorer

Construct an `ExplorerInput` (see `app/contracts/explorer.py`):

- `investigation_id`, `current_node`, `route`, `nodes`
- `available_tools` — the actual tool allow-list for this investigation.
  Explorer's output is validated against exactly this list, so Runtime
  controls Explorer's capability surface entirely through this field.
- `execution_budget` — caps how many steps Explorer may propose.
- `previous_actions` — feed back outcomes of prior tool executions
  (including failures) so Explorer doesn't repeat a failed approach.

## What Runtime gets back from Explorer

An `ExplorerOutput`. The two fields Runtime actually needs to act on:

- `selected_tool` / `parameters` / `command` — or call
  `explorer_output.to_tool_request()` to get a `ToolRequest` directly.
- `next_node` — which node the Planner/Runtime should advance the route
  to (or `None` if this was the last node).

Everything else (`purpose`, `reasoning`, `expected_observation`,
`success_condition`, `failure_condition`, `fallback`) is there for
Runtime's own logging, retry logic, or escalation decisions.

## The `RuntimeExecutor` interface

`app/adapters/runtime_adapter.py` defines the abstract shape Runtime is
expected to satisfy from the Agent System's point of view:

```python
class RuntimeExecutor(ABC):
    @abstractmethod
    def execute(self, tool_request: ToolRequest) -> Observation:
        ...
```

This interface is **not** used by the Agent System in production — the
Agent System never calls it against a real repository. It exists so:

1. The integration contract is documented in code, not just prose.
2. This subsystem's own tests/examples have a concrete (mocked)
   implementation to exercise the full pipeline offline
   (`app/adapters/mock_runtime.py`, `MockRuntimeExecutor`).

The real Runtime Engine does not need to literally subclass
`RuntimeExecutor` — it just needs to consume a `ToolRequest` and produce
whatever `Observation` shape it defines. `Observation` here is a
permissive placeholder (`dict` subclass); the actual schema is owned by
Runtime, not by this subsystem.

## What Runtime must provide to Verification

Construct a `VerificationInput` from the Claims Graph:

- `investigation_id`, `claims` (each with its `evidence`, tagged by
  `source` and `supports_claim`)
- Optionally `contradictory_evidence`, `relevant_goals`, `context`,
  `trust_information`

## What Runtime gets back from Verification

A `VerificationOutput`. Runtime is expected to:

- Use `supported_claims` / `weak_claims` / `contradictions` /
  `unresolved_claims` to decide what (if anything) to update in the
  Claims Graph or trust scores — **Verification does not do this itself**.
- Take `report_markdown` and write it (or a Runtime-composed superset of
  it) to `verification_report.md`. Verification produces the content;
  Runtime remains the authoritative report generator.

## Stability of the contract

`app/contracts/` is the integration surface. Other Wizard subsystems
should depend only on the Pydantic models there (or their JSON Schema /
equivalent in another language), not on any internal agent, prompt, or
validation code. As long as `ExplorerInput`/`ExplorerOutput` and
`VerificationInput`/`VerificationOutput` keep their field names and
types, Runtime and Planner can be developed and evolve independently of
this subsystem.
