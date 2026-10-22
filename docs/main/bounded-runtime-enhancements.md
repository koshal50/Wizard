# Bounded runtime enhancements

Baseline: `2873814`. No additional services, agents, packages or provider routes.

## Enable optional recovery and captures

The default execution flow remains unchanged. For a CLI session in PowerShell:

```powershell
$env:WIZARD_RECOVERY = '1'
$env:WIZARD_SCREENSHOTS = 'on_failure'
wizard
```

Use `checkpoints` instead of `on_failure` to also capture successful browser
checks. `off` disables captures. Runtime API options are `enable_recovery`,
`screenshots`, and `max_screenshots` (default 4, maximum 10). Setting these CLI
environment variables applies to new submissions; it does not alter saved runs.

## Dynamic work and one recovery round

Runtime remains the only execution authority. After an unmet check or an advisory
review requesting more evidence, it may ask the existing Planner once for a small
delta. Helpers target existing goals and cite real observations. Admission checks
unique IDs, dependencies/cycles, available capabilities, duplicate contracts and
the existing eight-check limit. At most three helpers can be proposed. Empty
recovery means there is no safe additional work, not success.

The ready-work selector uses passed dependencies and stable insertion order.
Helpers execute through the existing Explorer/Validator/Executor path. Original
assertions remain intact; helpers become prerequisites, not replacement proof.
Original results, recovery proposals, helper nodes, recheck permits and final
results are persisted. Reports distinguish requested goals from helper checks.

A previously failed command can receive one Runtime-authorized recheck after
its newly admitted dependencies produce successful proof. This permit only
affects exact-duplicate suppression: all command/path/capability/budget checks
still apply. Agents cannot request a permit or reset validator state.

Recovery does not retry provider failures or rate limits. It consumes the same
model/tool/time budgets and shared Cerebras gate. Verifier review is suppressed
when its proof/result fingerprint has not changed.

## Context and proof

The exact serialized context is selected against the instructions plus strict
schema size. Optional history and repository excerpts are removed before protected
requirements, current resources, available tools and latest results. If protected
content cannot fit, the request fails locally before a provider call. Selection
counts are recorded without storing full prompts. Character sizes are not exact
token measurements.

New browser predicates inspect observed role/name controls: `visible`, `enabled`
and `count`. Ambiguous state is unverified. HTTP `json_value` uses a JSON Pointer
against a bounded, successfully parsed, sanitized response. Missing, redacted or
truncated values cannot be silently recovered or used as proof. Text absence
cannot be established from a truncated excerpt.

Freshness uses actual observation order and resource identity, not arbitrary TTLs.
Navigation/mutations invalidate current browser candidates; process death and HTTP
connection failures invalidate matching current proofs. Superseding observation
IDs are exposed in evaluation results. Stored historical verdicts are retained:
normal cleanup does not erase proof that an operation worked during the run.
Current browser/process context includes its observation reference and indicates
omitted controls/text. Repeated-read detection ignores changing observation IDs.

## Screenshot artifacts

Capture uses the existing agent-browser command after normal Runtime validation.
Each successful PNG has an owner, goal/execution/observation association, byte
count and SHA-256. Captures are limited to 10 MB each and the investigation's
artifact/tool budgets. Invalid captures produce controlled failure, not evidence.
Diagnostic screenshots are excluded from agent progress comparisons and from
business assertion satisfaction.

Captures are withheld when configured private test inputs are active. Pixel data
is never sent to the text model or automatically uploaded. The local HTML report
links the actual images; exports copy only registered artifacts and verify hashes.
The artifact API serves allowlisted investigation-owned files, not arbitrary paths.

## Verification limits

Focused tests use deterministic agent policies and local targets, including real
commands, HTTP, Chromium snapshots and PNG capture. They do not prove a paid
model-driven sample-project run; that requires a separate user-run investigation.
