# Inline slash-command composer

The primary picker exposes exactly `investigate`, `verify`, `report`, `explain`.
Slash controls are not investigation command families. `/login` was previously
appended to the primary option list, with a special selection branch; a separate
help Window permanently rendered every registry description below the input.
Both integrations have been removed.

The existing prompt_toolkit TextArea now uses a registry-backed `SlashCompleter`
and a cursor-anchored floating Window. `SlashMenu` owns only highlighting/filtering;
prompt_toolkit owns painting, clipping and scrollbar. There is no second TUI,
input buffer, event loop, command dispatcher, or authentication implementation.

Type `/` at the command position to show the actual `SLASH_COMMANDS` entries:
`/login`, `/cancel-login`, `/status`, `/exit`. Filter with e.g. `/log`. Up/Down
move the highlight without rewriting the draft. Mouse-wheel input moves the
highlight with the scroll, preventing repaint from snapping back. PageUp/PageDown scroll through
longer menus. Enter fills the selected name and invokes the existing buffer
accept handler; displaying or highlighting a row never executes a command.
All currently supported slash controls are argument-free. Tab fills only, leaving
the composer editable; extra text is handled by the existing command validation.
Escape dismisses the popup and preserves draft/cursor. With the popup closed,
the existing Escape, navigation, processing, cancellation and submission behavior
remains in effect. From the primary picker, the existing `/` shortcut focuses this
same composer; it does not open another workflow.

Completion requires a single slash-command token at the start (optional leading
horizontal whitespace) with the cursor at its end. A slash in ordinary prose,
dates, URLs or paths never triggers a menu. Unsupported slash-prefixed submissions
retain the entire draft and show the existing Unknown command notice; they are
neither discarded nor sent to the planner. Argument-bearing/ordinary text is
not completed. The command registry remains the only source of names/descriptions;
no `/model`, `/permissions` or other unsupported command was added.

The popup shows up to eight rows, bounded by terminal height, with a scrollbar,
contrasting selected row, clipped single-line descriptions and automatic placement
above or below the input as room permits. It resizes with the terminal. The
permanent command-help footer is gone; a conditional notice Window still displays
existing error/draft/cancellation messages only when present. Token counters and
processing output are unchanged.

## Changed files for this TUI task

- `wizard/cli/tui/app.py`: remove fifth item/footer, attach the popup to the existing
  composer, add popup-scoped keyboard bindings and conditional notices.
- `wizard/cli/tui/slash_menu.py`: contextual lexical detection, live registry
  completion, highlight state, bounded scrolling and rendering.
- `wizard/tests/test_slash_menu.py`: real prompt_toolkit key-event/render coverage.
- `wizard/tests/test_tui_controls.py`: replace obsolete footer assertions with
  inline-registry/unknown-draft preservation checks.
- `wizard/tests/test_account_login.py`: update the old fifth-menu login test to
  verify composer access to the same login handler.
- `backend/README.md`: correct the TUI usage paragraph; backend API/security contract
  is unchanged.
- This document records behavior, scope and verification.

The checkout remains `fix/runtime-verification-integration`. All other prior work
is preserved, including eight pre-existing runtime/planner modifications and the
two untracked runtime investigation files. This task does not edit runtime-engine
logic, backend implementation, migrations, credential storage, provider/runtime
configuration, CLI transport, or the four command-family registry. Publication is a separate
step requiring the user's explicit authorization.

## Verification

```powershell
.\venv\Scripts\python.exe -m pytest wizard/tests/test_slash_menu.py wizard/tests/test_tui_controls.py wizard/tests/test_account_login.py -q --tb=short --basetemp=output/pytest-inline-slash-NEW_UNIQUE_SUFFIX
```

**56 passed, 2 skipped**. The skips are existing platform checks: Windows
Credential Manager has no logon session inside this sandbox; POSIX permissions
require a POSIX host. No authentication storage code changed in this task.

Tests exercise command-position filtering, registry descriptions, exactly four
primary choices, real Up/Down/Enter/Tab/Escape key events, selected login routing
to the existing worker, code entry/cancel behavior, status/exit dispatch, unchanged
ordinary intent submission, unknown slash draft preservation, and no permanent
help text. An expanded fixture registry (no production commands added) tests
scrolling, wheel events, paging and wrapping. Rendered screen coordinates verify the popup does not
cover the composer at 100/42/26/110-column layouts including a 12-row terminal.
Processing completion preserves an open popup, draft and input focus. Existing
closed-menu navigation and Escape are also tested.

```powershell
.\venv\Scripts\python.exe -m pytest wizard/tests -q --tb=short --basetemp=output/pytest-inline-slash-regression-NEW_UNIQUE_SUFFIX
```

**334 passed, 2 skipped, 10 failed**. This broader run preceded the final two
added closed-menu/processing-transition tests; both pass in the focused run above.
The ten failures are previously observed browser discovery, legacy Playwright
expectations, explain frontend hints, browser-tool narration and usage/runtime
interpreter configuration failures. They do not involve slash completion. These
areas and their earlier baseline failures are recorded in `backend/VERIFICATION.md`.
The full suite is not claimed green, and those unrelated issues were not changed.

```powershell
.\venv\Scripts\ruff.exe check wizard/cli/tui/slash_menu.py wizard/tests/test_slash_menu.py wizard/tests/test_tui_controls.py wizard/tests/test_account_login.py
.\venv\Scripts\ruff.exe format --check wizard/cli/tui/slash_menu.py wizard/tests/test_slash_menu.py wizard/tests/test_tui_controls.py wizard/tests/test_account_login.py
.\venv\Scripts\python.exe -m compileall -q wizard/cli/tui/app.py wizard/cli/tui/slash_menu.py
```

Scoped Ruff/format and compilation checks pass. The existing app module retains
its pre-existing unused frontend-suggestion import and broad-exception warnings;
new import ordering was fixed without reformatting unrelated app code. Scoped
`git diff --check` passes. The runtime/planner's original diff remains 233
insertions and 35 deletions across the same eight paths.

The UI tests run a real prompt_toolkit application/event loop with pipe input and
an in-memory terminal screen. No interactive native-terminal visual review or
comparison to attached screenshots was performed; no screenshots were available
in this session. The existing venv is editable, so restart `wizard` to see changes:

```powershell
.\venv\Scripts\Activate.ps1
wizard
```
