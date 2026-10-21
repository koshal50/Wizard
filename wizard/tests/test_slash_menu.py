"""Real prompt_toolkit key events and screen layout for composer slash commands."""

import asyncio

import pytest
from prompt_toolkit.application import create_app_session
from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.data_structures import Point, Size
from prompt_toolkit.document import Document
from prompt_toolkit.input import create_pipe_input
from prompt_toolkit.mouse_events import MouseButton, MouseEvent, MouseEventType
from prompt_toolkit.output import DummyOutput

from wizard.cli.parser.command_parser import SLASH_COMMANDS
from wizard.cli.tui.app import INTENT, MENU, WORKING, WizardTUI
from wizard.cli.tui.session import TuiSession
from wizard.cli.tui.slash_menu import SlashCompleter, slash_prefix


@pytest.mark.parametrize(
    "text,expected",
    [
        ("/", list(SLASH_COMMANDS)),
        ("/log", ["/login", "/logout"]),
        ("/login", ["/login"]),
        ("/status", ["/status"]),
        ("  /can", ["/cancel-login"]),
        ("/unknown", []),
        ("investigate architecture", []),
        ("Explain the date 24/10/24", []),
        ("What does 24/10/24 mean?", []),
        ("24/10/24", []),
        ("The path is D:/projects/Wizard", []),
        ("D:/projects/Wizard", []),
        ("https://example.com/api", []),
        ("/usr/local/bin", []),
        ("/login ordinary text", []),
        ("explain /login", []),
    ],
)
def test_only_the_command_position_and_prefix_can_complete(text, expected):
    completer = SlashCompleter(SLASH_COMMANDS)
    document = Document(text)
    assert [
        c.text for c in completer.get_completions(document, CompleteEvent())
    ] == expected
    assert document.text == text


def test_mid_token_cursor_and_multiline_paste_do_not_trigger_or_rewrite():
    assert slash_prefix(Document("/login", cursor_position=2)) is None
    assert slash_prefix(Document("\n/login")) is None
    assert slash_prefix(Document("/login\n")) is None


class Terminal(DummyOutput):
    dimensions = Size(rows=34, columns=100)

    def get_size(self):
        return self.dimensions


async def until(predicate):
    deadline = asyncio.get_running_loop().time() + 3
    while not predicate():
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError("TUI did not reach the expected state")
        await asyncio.sleep(0.01)


def run_ui(scenario, state=INTENT):
    async def run():
        with (
            create_pipe_input() as keys,
            create_app_session(input=keys, output=Terminal()) as session,
        ):
            ui = WizardTUI()
            ui.state = state
            if state != MENU:
                ui.family, ui.target = "investigate", "architecture"
                ui.app.layout.focus(ui.input)
            if state == WORKING:
                ui.session = TuiSession("investigate", "architecture", running=True)
            ui.app.ttimeoutlen = 0.01
            ui.app.timeoutlen = 0.05
            task = asyncio.create_task(ui.app.run_async())
            try:
                await until(
                    lambda: (
                        ui.app.is_running
                        and ui.app.renderer.last_rendered_screen is not None
                    )
                )
                await scenario(ui, keys, session.output)
            finally:
                if ui.app.is_running and not ui.app.is_done:
                    ui.app.exit()
                await asyncio.wait_for(task, 3)

    asyncio.run(run())


def screen_text(ui):
    screen = ui.app.renderer.last_rendered_screen
    return "\n".join(
        "".join(cell.char for _, cell in sorted(row.items()))
        for _, row in sorted(screen.data_buffer.items())
    )


def test_only_four_primary_commands_and_no_persistent_slash_help():
    async def check(ui, keys, terminal):
        assert ui._current_options() == ["investigate", "verify", "report", "explain"]
        initial = screen_text(ui)
        assert "/login" not in initial
        for description in SLASH_COMMANDS.values():
            assert description not in initial
        assert not ui.slash_menu.visible
        keys.send_text(
            "/"
        )  # Existing shortcut focuses the same composer from the menu.
        await until(lambda: ui.slash_menu.visible)
        assert ui.app.layout.has_focus(ui.input)
        assert ui._current_options() == ["investigate", "verify", "report", "explain"]

    run_ui(check, MENU)


def test_arrows_highlight_without_rewriting_and_escape_preserves_draft_cursor(
    monkeypatch,
):
    async def check(ui, keys, terminal):
        cancelled = []
        ui.session.cancel = lambda: cancelled.append(True)
        keys.send_text("/")
        await until(lambda: ui.slash_menu.visible)
        assert ui.slash_menu.selected == 0
        before = ui.input.buffer.document
        keys.send_text("\x1b[B")
        await until(lambda: ui.slash_menu.selected == 1)
        assert ui.input.buffer.document == before
        assert any(
            "selected" in style and "/logout" in text
            for style, text in ui.slash_menu.fragments()
        )
        keys.send_text("\x1b[A")
        await until(lambda: ui.slash_menu.selected == 0)
        keys.send_text("\x1b")
        await until(lambda: not ui.slash_menu.visible)
        assert ui.input.buffer.document == before
        assert ui.state == WORKING and not cancelled and ui.session.running
        keys.send_text("logi")
        await until(lambda: ui.slash_menu.visible and len(ui.slash_menu.entries) == 1)
        assert ui.slash_menu.entries[0].text == "/login"

    run_ui(check, WORKING)


def test_enter_selected_login_reaches_existing_worker_once_and_cancel_is_preserved(
    monkeypatch,
):
    calls = []

    class Worker:
        running = True

        def __init__(self, notify):
            self.notify = notify

        def start(self):
            calls.append("login")

        def submit(self, code):
            calls.append(("code", code))

        def cancel(self):
            calls.append("cancel")

    monkeypatch.setattr("wizard.cli.account_login.LoginWorker", Worker)

    async def check(ui, keys, terminal):
        keys.send_text("/log")
        await until(lambda: ui.slash_menu.visible and ui.input.text == "/log")
        assert not calls  # Displaying/highlighting never executes anything.
        keys.send_text("\r")
        await until(lambda: calls == ["login"])
        assert ui.input.text == ""
        keys.send_text("ABCD1234ABCD\r")
        await until(lambda: len(calls) == 2)
        assert calls[1] == ("code", "ABCD1234ABCD")
        keys.send_text("/cancel-login")
        await until(lambda: ui.slash_menu.visible and ui.input.text == "/cancel-login")
        keys.send_text("\r")
        await until(lambda: calls[-1] == "cancel")

    run_ui(check, WORKING)


def test_tab_fills_only_and_argument_draft_stays_in_the_existing_composer(monkeypatch):
    calls = []
    monkeypatch.setattr(
        WizardTUI, "_start_account_login", lambda self: calls.append("login")
    )

    async def check(ui, keys, terminal):
        keys.send_text("/log")
        await until(lambda: ui.slash_menu.visible and ui.input.text == "/log")
        keys.send_text("\t")
        await until(lambda: ui.input.text == "/login" and not ui.slash_menu.visible)
        assert not calls
        keys.send_text(" extra text")
        await until(lambda: ui.input.text == "/login extra text")
        assert not ui.slash_menu.visible
        keys.send_text("\r")
        await until(lambda: "Unknown command" in ui._input_notice)
        assert ui.input.text == "/login extra text" and not calls

    run_ui(check)


def test_status_and_exit_use_existing_dispatchers(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "wizard.cli.runtime_client.usage.status",
        lambda **kwargs: calls.append("status") or {},
    )
    monkeypatch.setattr(
        "wizard.cli.display.usage.format_status", lambda data: "persisted token usage"
    )

    async def check(ui, keys, terminal):
        keys.send_text("/status")
        await until(lambda: ui.slash_menu.visible and ui.input.text == "/status")
        keys.send_text("\r")
        await until(
            lambda: ui._usage_report and "persisted token usage" in ui._usage_report
        )
        assert calls == ["status"]
        assert not ui.slash_menu.visible
        assert ui.app.layout.has_focus(ui.body)
        keys.send_text("/exit")
        await until(lambda: ui.slash_menu.visible and ui.input.text == "/exit")
        keys.send_text("\r")
        await until(lambda: ui._exiting)

    run_ui(check)


@pytest.mark.parametrize(
    "text",
    [
        "investigate architecture",
        "Explain the date 24/10/24",
        "What does 24/10/24 mean?",
        "The path is D:/projects/Wizard",
        "https://example.com/api",
    ],
)
def test_ordinary_text_is_submitted_unchanged(monkeypatch, text):
    submitted = []
    monkeypatch.setattr(
        WizardTUI, "_begin_work", lambda self, value: submitted.append(value)
    )

    async def check(ui, keys, terminal):
        keys.send_text(text)
        await until(lambda: ui.input.text == text)
        assert not ui.slash_menu.visible
        keys.send_text("\r")
        await until(lambda: bool(submitted))
        assert submitted == [text]

    run_ui(check)


def test_unknown_slash_input_remains_editable_without_running_a_planner(monkeypatch):
    submitted = []
    monkeypatch.setattr(
        WizardTUI, "_begin_work", lambda self, text: submitted.append(text)
    )

    async def check(ui, keys, terminal):
        text = "/unknown ordinary text 24/10/24"
        keys.send_text(text + "\r")
        await until(lambda: "Unknown command" in ui._input_notice)
        assert ui.input.text == text and not ui.slash_menu.visible and not submitted
        keys.send_text(" more")
        await until(lambda: ui.input.text == text + " more")

    run_ui(check)


def test_popup_scrolls_and_resizes_above_processing_composer_without_overlap(
    monkeypatch,
):
    # Fixture-only registry expansion tests scrolling without adding production commands.
    for index in range(24):
        monkeypatch.setitem(
            SLASH_COMMANDS, f"/test-{index:02}", f"Fixture command {index}"
        )

    async def check(ui, keys, terminal):
        keys.send_text("/")
        await until(lambda: ui.slash_menu.visible)
        assert ui.slash_menu.height() == 8
        keys.send_text("\x1b[A")  # Wrap to the last item; cursor stays in the composer.
        await until(lambda: ui.slash_menu.selected == len(SLASH_COMMANDS) - 1)
        ui.app.invalidate()
        await until(lambda: ui.slash_menu.window.vertical_scroll > 0)
        last = len(SLASH_COMMANDS) - 1
        keys.send_text("\x1b[5~")
        await until(lambda: ui.slash_menu.selected == last - ui.slash_menu.height())
        keys.send_text("\x1b[6~")
        await until(lambda: ui.slash_menu.selected == last)
        wheel = MouseEvent(
            position=Point(0, 0),
            event_type=MouseEventType.SCROLL_UP,
            button=MouseButton.NONE,
            modifiers=frozenset(),
        )
        assert ui.slash_menu.control.mouse_handler(wheel) is None
        ui.app.invalidate()
        assert ui.slash_menu.selected == last - 1 and ui.input.text == "/"
        for rows, cols in [(18, 42), (12, 26), (36, 110)]:
            terminal.dimensions = Size(rows=rows, columns=cols)
            ui.app._on_resize()
            await asyncio.sleep(0.06)
            screen = ui.app.renderer.last_rendered_screen
            positions = screen.visible_windows_to_write_positions
            popup, composer = (
                positions[ui.slash_menu.window],
                positions[ui.input.window],
            )
            assert (
                popup.ypos + popup.height <= composer.ypos or popup.ypos > composer.ypos
            )
            assert popup.xpos >= 0 and popup.xpos + popup.width <= cols
            assert popup.height <= rows and composer.height == 1
            assert ui.input.text == "/" and ui.session.running
        keys.send_text("\x1b")
        await until(lambda: not ui.slash_menu.visible)
        assert ui.input.text == "/" and ui.session.running

    run_ui(check, WORKING)


def test_closed_popup_preserves_primary_navigation_and_escape():
    async def check(ui, keys, terminal):
        keys.send_text("\x1b[A")
        await until(lambda: ui.selected == 3)
        keys.send_text("\x1b[B")
        await until(lambda: ui.selected == 0)
        keys.send_text("\r")
        await until(lambda: ui.menu_level == "target")
        assert ui.family == "investigate" and not ui.slash_menu.visible
        keys.send_text("\x1b")
        await until(lambda: ui.menu_level == "family")
        assert ui.state == MENU

    run_ui(check, MENU)


def test_processing_completion_keeps_open_menu_and_draft(monkeypatch):
    async def check(ui, keys, terminal):
        monkeypatch.setattr(ui, "_record_history", lambda snapshot: None)
        keys.send_text("/lo")
        await until(lambda: ui.slash_menu.visible and ui.input.text == "/lo")
        before = ui.input.buffer.document
        ui.session.finished = True
        ui.session.running = False
        ui._sync_finished()
        await asyncio.sleep(0.06)
        assert ui.slash_menu.visible and ui.input.buffer.document == before
        assert ui.app.layout.has_focus(ui.input)
        assert not ui.input.read_only()

    run_ui(check, WORKING)
