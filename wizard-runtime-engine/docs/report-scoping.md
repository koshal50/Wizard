# Command-scoped reports (schema 2)

The layout follows `wizard_dynamic_intent_report_template.md` in the workspace root. Pandoc-only raw HTML fences, instructional comments and placeholders are not emitted. Markdown tables and native HTML `<details>` provide expandable provenance, execution and graph sections.

## Existing flow and minimal changes

CLI `command_parser.COMMAND_TARGETS` validates the selected family/target; intent parsing preserves additional named targets, URLs and the free-text question. Handlers assemble the request; Runtime stores `intent`, `targets`, `question`, goals, graph, observations and claims. The existing Verifier call receives requirements and evidence. All Runtime exits call `control.report.generate`, persist `verification_report.md`, and the report API/TUI retrieves/copies that artifact.

`report.generate` now delegates to one read-only `ReportContext` projection and scoped renderer. `generate_diagnostics` remains the existing opt-in diagnostic interface. Goal calculation, Planner decisions, resource lifecycle and CLI handlers are unchanged. The Verifier receives the same subject contract used by the renderer; no formatting-only model call is added. Model narrative is admitted only after section, observation/claim reference, inspected path and final-state checks. Deterministic state and provenance remain authoritative; rejected narrative stays in `model_report.md` for diagnostics.

## Authoritative mapping

The CLI implementation, not descriptions of future commands, is authoritative. A regression compares this mapping with the parser.

| Subject | Families | Primary report sections |
|---|---|---|
| architecture | investigate, explain | Stack; components; observed imports/relationships; inspected structure; relevant external modules; gaps |
| api | investigate, verify | Framework; literal route declarations/handlers; request fields/status declarations; middleware references; HTTP attempts; gaps |
| runtime | investigate, verify, explain | Startup/liveness/readiness levels; entry points/scripts; initialization/configuration; runtime dependencies |
| deployment | investigate, verify, explain | Manifests; service/environment declarations; actual deployment attempts; gaps |
| authentication | investigate | Identity/session source signals; middleware references; authorization-related route declarations; gaps |
| security | investigate, verify, explain | Evidence-backed source signals; checks actually performed; unresolved risks (no invented severity) |
| build | investigate | Declared build commands; build configuration; actual build attempts |
| dependencies | verify, explain | Manifest declarations; installation/resolution checks; gaps |
| containers | verify | Container configuration; actual build/run attempts; gaps |
| ci | verify | Workflow declarations; checks/execution; gaps |
| existing state (no target) | report | Supplied goal results and evidence-backed existing knowledge; no architecture fallback |

`investigate` explains discovered implementation; `verify` emphasizes executed checks and authoritative completion criteria; `explain` preserves the existing read-only inspection flow. The existing `report` handler creates a report-family request with no target; it does not supply a prior investigation ID. This change does not make it load another investigation or rerun one. Empty supplied state is explicitly reported as unavailable. Fetching a completed investigation's report continues to return its saved artifact.

## Integrity and limitations

Observation and claim ownership is filtered to one investigation; references are deduplicated. Source/configuration inference never proves successful execution. Contradictory relationships and contradictory evidence remain unresolved, with original trust and provenance values. Incomplete state is explicit even when independent checks passed. Raw evidence and graph details are expandable rather than a universal body.

Literal Express-style registration and Python `app.get`/router decorators are recognized conservatively. Dynamic routes, router mount prefixes, full schemas and handler dependencies require traced evidence; no endpoint, topology diagram, service availability or vulnerability is invented. Model citation checks do not constitute independent proof of arbitrary prose: admitted analysis is labeled inference, and Runtime evidence/criteria control verified results.

## Validation and examples

- `python -m pytest wizard-runtime-engine/tests/test_scoped_reports.py wizard-runtime-engine/tests/test_phase5_report.py -q`: **44 passed** (including 29 scoped-rendering tests).
- Agent suite, run from `wizard_agents/wizard_agents` with Runtime `src` on `PYTHONPATH`: **63 passed**, including report-contract and observation-reference adapter tests.
- `python -m pytest wizard/tests -q`: **254 passed**.
- Full Runtime suite: **409 passed, 2 failed**. Failures were `test_timeout_kills_real_owned_process_and_closes_browser` and `test_local_sandbox_timeout`, involving Windows `taskkill` termination. The former passed in isolation; the latter still failed because `taskkill` exceeded its existing two-second timeout. A broader focused run had **83 passed, 1 failed**, with another process-cleanup assertion in `test_foreground_service_timeout_schedules_one_distinct_owned_recovery`. Process lifecycle implementation was not changed for this report task.
- Ruff lint and formatting checks pass for the new report modules, scoped tests and example generator; the report prompt also passes lint. A broader lint check exposes existing diagnostics-renderer and adapter style findings; those unrelated sections were not refactored.
- The [architecture](report-examples/architecture.md), [API](report-examples/api.md), and [incomplete runtime](report-examples/incomplete-runtime.md) examples re-render original persisted state. They are not new live/provider acceptance runs. See [provenance and regeneration instructions](report-examples/README.md).

Examples were inspected for subject relevance, original final state, citation ownership, literal route locations, startup versus readiness, valid Markdown tables, balanced `<details>`, control characters and unresolved placeholders. All structural checks passed. Expanders require a Markdown viewer supporting native HTML; the renderer does not introduce a separate interactive web app. Existing stored reports are not silently overwritten.
