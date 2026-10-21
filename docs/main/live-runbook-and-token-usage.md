# Live runbook and token usage

The Runtime publishes exact, provider-reported token totals through the existing
usage SSE connection immediately after a response. While a request is in progress,
the last confirmed totals remain visible with an activity indicator. Non-streaming
providers do not expose an exact token-by-token count during generation.

Local durable snapshots work without PostgreSQL. PostgreSQL remains optional for
historical/account aggregation. Local fallback history is labeled as runs recorded
on this machine. Unknown usage is marked incomplete; reconnect snapshots replace,
rather than add to, the visible counters.

## Report controls

- F3 / Live report: toggle between the investigation activity and current runbook.
- F4 / Open report/map: open the exported offline HTML after completion.
- F5 / Rerun: submit the same intent as a new normal investigation. This consumes
  provider capacity/credits and uses fresh validation, processes and browser state.
- F6 / Copy commands: copy the recorded startup/execution commands. Review their
  working directories and replace redacted configuration before running manually.

The same actions are clickable in the report toolbar. Commands embedded in Markdown
are never executable links. Recorded browser references and credentials are never
replayed. All automatic reruns use the existing Runtime path.

## Artifacts

The existing Markdown report remains in the project's output folder. Companion
`<investigation-id>.runbook.json` and `<investigation-id>.runbook.html` files contain
structured evidence and an offline diagram. Runtime copies are persisted in the
investigation directory as `runbook.json` and `runbook.html`.

Reports distinguish verification results, recorded startup commands, execution
history, evidence identifiers, blockers and cleanup. An execution map shows actual
check/tool/observation links. The application map reuses the existing evidence-backed
architecture exporter; source-supported connections remain labeled inferred. Missing
connections, screenshots or runtime proof are never fabricated.

Report generation is deterministic and makes no model requests. HTML is escaped,
self-contained and read-only; it needs no website service, upload or diagram server.
