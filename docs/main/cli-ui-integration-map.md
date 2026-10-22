# Native CLI presentation integration

## Current checkpoint

The Textual shell is now the default interactive `wizard` interface. Set
`WIZARD_UI=classic` to select the previous interface explicitly. Opening it performs
no investigation, account authorization, service startup, or provider request.
`/login` reuses LoginWorker. Enter in the composer submits the selected check:
it connects ServiceSupervisor, then starts one existing TuiSession. No separate
Start/Stop buttons remain; Ctrl+C or `/cancel` cancels through that session.
The live view projects session notifications on Textual's UI thread, with bounded
activity, expandable browser/activity details, reported token totals, real
cancellation and final report paths. Exit uses the existing session shutdown and
stops only owned services after Textual releases the terminal. These connections
were checked with local substituted services/event playback, not a real run.

First use offers a skippable tour, optional account login, and responsive code
cells. Display preferences are stored locally outside the repository, without
credentials. `/help` reopens guidance; `/guide` toggles the companion.
The Quit freeze was a collision with Textual's private `_closing` flag; Wizard
now uses `_ui_closing`, leaving Textual's exit-message lifecycle intact. Service
startup accepts cancellation and retains owned process handles for cleanup.
The existing event stream now carries bounded, sanitized `tool.observed` output
after observation persistence, including process-readiness output changes.

Validation checkpoint: 58 focused UI/session/usage/scoped-report tests passed.
The existing `test_runtime_schedules_bounded_readiness_without_browser` still
fails: its mocked Planner/Explorer graph never queues the expected HTTP readiness
probe, so the investigation remains incomplete. A missing process-observation
collection in context packaging and a report failure-keyword mismatch were fixed
when these checks exposed them. HTTP scheduling/verification policy was not
rewritten to make the test pass. No real-provider investigation was run; native
frontend checks must not be read as proof of full Runtime end-to-end success.

## Existing boundaries to reuse

Additional connected actions: `/status` reads the existing usage endpoint off
the UI thread, `/logout` uses existing revocation, and `/btw` uses SideChat's
existing transport with main/side navigation, fresh conversation and explicit
clipboard actions. Opening side chat does not call a model; sending a question
does. Account changes close old side conversations and invalidate usage views.
Returned reports render as Markdown, with first observed page controls exposed
in an expandable view. This is a presentation of actual supplied state; empty
views do not manufacture browser or execution results. Local playback checks
passed; no real endpoint/provider execution was performed for this checkpoint.

| Feature | Existing owner | UI connection |
| --- | --- | --- |
| CLI arguments and noninteractive commands | `wizard/cli/main.py` | Preserve existing dispatch; no new command registry |
| Interactive launch | `wizard/cli/tui/app.py:run_tui` | Native by default, before any service launch; classic is an explicit override |
| Command/subcommand names | `wizard/cli/parser/command_parser.py:COMMAND_TARGETS` | Native buttons derive from this registry |
| Slash command names | `wizard/cli/parser/command_parser.py:SLASH_COMMANDS` | Existing account/status/chat handlers are connected; help/guide/cancel are local UI controls |
| Intent interpretation | `wizard/cli/parser/intent_parser.py:parse_intent` | Used locally when reviewing input |
| Canonical intent | `wizard/cli/parser/intent_builder.py:build_intent` | Prepared without submission or model calls |
| Services and owned-process cleanup | `wizard/cli/tui/services.py:ServiceSupervisor` | Start explicitly, off the UI thread; never during shell construction; stop owned services on exit |
| Investigation worker and cancellation | `wizard/cli/tui/session.py:TuiSession` | Reused for submission and cancellation; notifications marshal into Textual messages |
| Events and snapshots | `TuiSession.snapshot`, `snapshot_activity` | Current narration is not the final modern projection; show user actions and results, not module names |
| Login authorization | `wizard/cli/account_login.py:LoginFlow`, `LoginWorker` | Reused request/approval/exchange; centred code view is connected |
| Credential removal | `wizard/cli/account_logout.py:logout` | Reuse revocation and secure removal; do not confuse browser and CLI sessions |
| Side conversation | `wizard/cli/tui/side_chat.py:SideChat` | Explicit user action only; no model for companion status |
| Usage/report/account transport | `wizard/cli/runtime_client/` | Keep existing data boundaries; no fabricated values |
| Reports and artifact references | Existing runtime runbook/report and session fields | Reuse saved state; opening a report never submits work |
| Native mascot display | `wizard/cli/tui/reaper_widget.py` | Complete 192x208 cached frames passed to textual-image; detected Sixel/TGP image rendering, no automatic coarse text replacement; source credit; no implicit network request |

## Ownership during migration

- Textual owns the terminal for the new shell. Do not mount Prompt Toolkit inside it.
- The old application remains available for parity review, not as a hidden fallback
  after a new-shell execution failure.
- Runtime remains the only execution authority. No UI button executes arbitrary
  commands directly, manufactures ToolRequests, or changes verification outcomes.
- The optional `tui` dependency installs Textual; image protocol libraries are not
  required for the initial shell and are not installed.
- The shell has no pretend token usage, connection status, live output, or results.

## Local visual review

Actual Textual screenshots are `cli-textual-main.svg`, `cli-textual-selected.svg`,
`cli-textual-subcommands.svg`, `cli-textual-slash.svg`, and `cli-textual-review.svg` in this directory. They were captured headlessly with
Textual's UI driver, with no running services. They are presentation artifacts,
not execution evidence.

Optional manual launch from the Wizard directory:

```powershell
& .\wizard-runtime-engine\.venv\Scripts\python.exe -m wizard.cli.tui.textual_app
```

This opens only the UI shell. Select a check, add an optional intent, and Enter runs it.
Normal interactive `wizard` now selects the native interface. Noninteractive
commands keep their existing dispatch. `WIZARD_UI=classic` selects the old UI.

`cli-textual-activity.svg` is a local event-playback screenshot, not real execution
evidence. Report actions open saved output, copy recorded commands, rerun through
normal submission, and inspect connections. Upload requires a separate explicit
approval with the destination shown; report links cannot execute commands. The live
panel displays events and snapshots supplied by the existing session; it does
not promise stdout streaming when the Runtime has not emitted that data.

The latest shell stacks commands vertically and replaces the family list with
subcommands on selection. It explains both levels through the small real cached
reaper. Commands returns to the main list. Motion off pauses the character and
header animation. Slash suggestions complete the draft without starting work.

For a machine without the user-requested artwork cached, explicit local setup is:

```powershell
& .\wizard-runtime-engine\.venv\Scripts\python.exe -m wizard.cli.tui.reaper_widget
```

This downloads only the official sprite sheet to the user's cache, with bounded
size and image-layout validation. It does not bundle artwork or change the
verification runtime. Asset redistribution terms remain a separate concern.

Full image display needs a compatible terminal, not just a compatible shell.
Windows Terminal 1.22+ supports Sixel. In VS Code the library documents the
terminal.integrated.enableImages setting. Unsupported graphics show an
explanation instead of a misleading low-resolution mascot. The explicit
WIZARD_REAPER_RENDERER override can be auto, sixel, tgp, or halfcell; force a bitmap
protocol only when terminal support is known. Bitmap content is not captured by
the ordinary SVG screenshot export, so earlier SVGs are not proof of this fix.

Keyboard: arrows navigate command/subcommand lists, Enter selects, Tab moves
focus, Page Up/Page Down scroll output, and Ctrl+Home/Ctrl+End jump through it.
Slash suggestions keep their own arrow/completion behavior when open.
