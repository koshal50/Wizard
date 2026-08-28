# Explorer Agent

## Purpose

Explorer decides **how** the Runtime should investigate a single
Investigation Node. It reasons about which tool to use, what parameters
to pass, what evidence to expect, and what node to move to next. It
produces a plan only — it never executes anything.

## Contract

See `app/contracts/explorer.py` for the full Pydantic schemas.

### `ExplorerInput`

| Field | Type | Notes |
|---|---|---|
| `investigation_id` | str | |
| `current_node` | `InvestigationNode` | must be present in `route.node_order` |
| `route` | `Route` | ordered `node_order` + `current_index` |
| `nodes` | `list[InvestigationNode]` | full node set, for cross-node context |
| `active_goals` | `list[str]` | |
| `known_claims` | `list[str]` | short text summaries |
| `context` | `str \| None` | free text |
| `missing_evidence` | `list[str]` | |
| `previous_actions` | `list[PreviousAction]` | including failures |
| `available_tools` | `list[ToolName]` | Explorer may only select from this list |
| `repository_metadata` | `RepositoryMetadata \| None` | |
| `execution_budget` | `ExecutionBudget` | `max_steps`, `max_tool_calls`, optional time budget |

### `ExplorerOutput`

| Field | Type | Notes |
|---|---|---|
| `investigation_id`, `node_id` | str | must match the input |
| `purpose` | str | why this step matters |
| `reasoning` | str | Explorer's reasoning trace |
| `selected_tool` | `ToolName` | must be in `available_tools` |
| `parameters` | dict | |
| `command` | str \| None | only valid when `selected_tool == execute_command` |
| `execution_steps` | `list[ExecutionStep]` | ordered, within `execution_budget.max_steps` |
| `expected_observation` | str | |
| `success_condition` / `failure_condition` | str | |
| `next_node` | str \| None | must be a known node id, or `None` if terminal |
| `fallback` | str \| None | escalation guidance |

## What Explorer must never do

- Execute commands or tools
- Access the repository or sandbox directly
- Modify observations
- Create or modify claims / the Claims Graph
- Calculate or modify trust
- Mark goals complete
- Generate the final report

These are enforced structurally (Explorer's code has no filesystem or
subprocess access) and by validation (`app/validation/explorer_validation.py`
rejects output referencing tools/nodes that weren't supplied).

## Validation pipeline

1. **Pydantic parsing** — the LLM's JSON response must parse into
   `ExplorerOutput` or the call fails (`LLMError` / `ExplorerAgentError`).
2. **Semantic validation** (`validate_explorer_output`) —
   - `investigation_id` / `node_id` match the input
   - `selected_tool` and every step's `tool` are in `available_tools`
   - `next_node` is a known node id (or `None`)
   - step count respects `execution_budget.max_steps`
   - steps are ordered and non-duplicated
   - `command` is only present for `execute_command`

Any failure raises `ExplorerAgentError` — callers (including the API
layer) treat this as a 422 rather than silently accepting bad output.

## Tool registry

Explorer may only request tools Runtime has declared available via
`ExplorerInput.available_tools`. The canonical tool list and their
expected parameters live in `app/explorer/tools.py`:

`read_file`, `search_files`, `list_directory`, `execute_command`,
`inspect_configuration`, `trace_execution`.

These are **requests only** — Explorer's tool registry module contains no
execution logic.
