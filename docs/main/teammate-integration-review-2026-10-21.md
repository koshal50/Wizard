# Teammate integration review — 2026-10-21

## Subsequent runtime rollback

The integration results below describe the earlier candidate, not proof of a live successful investigation. After `inv_47008cec973e` stopped on identical browser snapshots, the core runner, assertion evaluator, validator, tactical contracts and role prompts were restored from the working `8c3161f` baseline. The standalone website/account code was retained. Native side-chat transport, provider-gate deadlines and strict read-only explanation planning were preserved as small compatibility changes. Experimental repository refinement/reuse and architecture synthesis are no longer connected to the normal runner; their incoming feature-specific tests are not baseline acceptance coverage and require reconciliation before those features are reintroduced.

The outgoing source files were preserved locally under `.wizard/recovery/pre-pull-runtime-restore`. A bounded unchanged-browser-read feedback path was added: identical consecutive page reads retain their observations but suppress further redundant snapshot/extract choices until the observed page changes. Explorer receives the reason and actual controls; no action or success is fabricated. The new regression exercises this recovery through real local browser actions with a deterministic test policy, without provider calls. A separate live model-driven run has not been performed.

## Recovery points and worktrees

- Working CLI/kernel baseline: `8c3161f`, retained as `backup/working-wizard-2026-10-21`.
- Incoming CLI/kernel commits: `de29af8`, `98ec7ce`, `68efd2f`, `b0b9936`, `fe97966`, `c3c8d0d`.
- Website worktree: sibling `wizar-web`, branch `wizar-web`, tracking `origin/wizar-web` at `5b97ab9`.
- Incoming changes were inspected and checked in an isolated `wizard-integration-review` worktree before advancing the working branch.

## Kept

- Grounded repository refinements and reusable successful repository observations.
- Read-only explanation schemas and execution restrictions.
- Controlled assertion evaluation errors and case-sensitive/case-insensitive predicates.
- Deadline-aware waits through the existing shared Cerebras rate gate.
- Explicit architecture investigations, evidence-backed diagram exports and consent-gated website uploads.
- Optional website account authorization, secure credential storage and account-scoped usage ownership.
- Slash menus, side conversations, UI clipboard actions and their existing regressions.
- Existing process, browser, validation, observation, cleanup and native agent architecture.

These capabilities have separate scopes. An architecture explanation is not runtime verification, source evidence cannot prove a browser result, and a website account is not required for a local investigation.

## Corrected before integration

1. **Optional account stack on normal startup:** incoming `build_specs` prepended the account backend and website. Normal verification now starts the kernel alone. `WIZARD_ACCOUNT_AUTOSTART=1` explicitly enables the local website stack; `wizard /login` retains explicit local account startup. TUI `/login` can use an already-running/remote account service, or the opt-in local stack. No account/database requirement is introduced for local verification.
2. **Website checkout path:** discovery accepts the requested sibling `wizar-web/wizardsite`, retaining compatibility with an existing `Wizard-web/wizardsite` and the explicit directory override. The editor workspace points to the new worktree.
3. **Clipboard dependency:** a missing optional clipboard package no longer prevents importing its UI helper. Unavailable copy/paste returns a controlled message and normal terminal paste remains available. The package is an optional install extra.
4. **Context growth:** repository evidence metadata is limited to 16 recent/preferred reads. Content remains budgeted; observed browser state lowers the repository excerpt budget to 4,000 characters so repository history does not crowd out the live page.
5. **Partial reads:** reads that reach the requested byte limit are conservatively marked truncated. They cannot be represented as complete file content or reused as complete cached reads.
6. **Repository mutations on command failure:** cached repository reads are invalidated after command/process attempts even when the operation fails, since a failed command can still modify files.
7. **Windows usage spool paths:** long side-conversation run IDs were embedded in filenames and staging filenames. Short unique filenames retain the run identity in the JSON payload and avoid the observed accounting-write failure. The previously failing side-conversation accounting test passes with this change.
8. **Test isolation:** optional account backend tests remain explicitly selectable instead of becoming a new default prerequisite of the CLI test command.

## Validation boundaries

The focused checks exercise the native Runtime, process/browser fakes and existing real local-process tests, repository refinement/reuse, architecture grounding/export, account transport and ownership, side conversations, menus, clipboard failure handling and TUI controls. No real Cerebras request or Wizard investigation was run. Unit/mocked checks do not prove a live account deployment or a new real signup/login investigation.

Results: the combined focused run passed 297 tests with two optional-dependency skips. A subsequent focused run passed all 37 startup/refinement tests, including two additional regressions added after the combined run. Existing browser acceptance tests also exercised the real agent-browser implementation against their local test application with deterministic test policies; this does not substitute for a real model-driven sample-project investigation.

The separate account backend test collection requires `psycopg`, which is not installed in the available interpreter. No dependencies were installed and no PostgreSQL service was started. Clipboard-library-specific coverage is skipped when its optional package is unavailable; terminal UI and missing-package behavior are still tested.

The working baseline and teammate commit history are both preserved. No changes were pushed as part of this integration.
