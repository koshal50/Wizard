"""Actual key events copy/paste drafts without submitting or quitting."""

import pytest
from test_slash_menu import run_ui, screen_text, until

from wizard.cli.tui import clipboard
from wizard.cli.tui.app import MENU


def test_clicking_startup_input_keeps_j_k_and_enter_out_of_menu_navigation():
    async def check(ui, keys, terminal):
        assert not ui._status_input
        position = (
            ui.app.renderer.last_rendered_screen.visible_windows_to_write_positions[
                ui.input.window
            ]
        )
        x, y = position.xpos + 4, position.ypos + 1
        keys.send_text(f"\x1b[<0;{x};{y}M\x1b[<0;{x};{y}m")
        await until(lambda: ui.app.layout.has_focus(ui.input))
        assert not ui._status_input  # A click changes focus, not slash-command state.
        keys.send_text("hello world")
        await until(lambda: ui.input.text == "hello world")
        keys.send_text("\x1b[D" * 5 + "jk")
        await until(lambda: ui.input.text == "hello jkworld")
        assert ui.selected == 0 and ui.menu_level == "family"
        keys.send_text("\r")
        await until(lambda: ui._status_input)
        assert ui.state == MENU and ui.family is None
        assert ui.input.text == "hello jkworld"

    run_ui(check, MENU)


@pytest.mark.parametrize("terminal_paste", [False, True])
def test_paste_from_startup_menu_focuses_input_and_renders_without_another_key(
    monkeypatch, terminal_paste
):
    text = "Paste visible immediately jk"
    monkeypatch.setattr(clipboard, "read_text", lambda: text)

    async def check(ui, keys, terminal):
        assert ui.app.layout.has_focus(ui.body)
        keys.send_text("\x1b[200~" + text + "\x1b[201~" if terminal_paste else "\x16")
        await until(lambda: text in screen_text(ui))
        assert ui.input.text == text
        assert ui.app.layout.has_focus(ui.input)
        assert ui.selected == 0 and ui.family is None
        keys.send_text("\x1b[D" * 2 + "jk")
        await until(lambda: ui.input.text == text[:-2] + "jk" + text[-2:])
        assert ui.selected == 0 and ui.family is None

    run_ui(check, MENU)


def test_select_all_copy_and_paste_unicode_draft(monkeypatch):
    system = {"text": ""}
    monkeypatch.setattr(clipboard, "write_text", lambda text: system.update(text=text))
    monkeypatch.setattr(clipboard, "read_text", lambda: system["text"])

    async def check(ui, keys, terminal):
        text = "Explain café — auth 🔑"
        keys.send_text(text)
        await until(lambda: ui.input.text == text)
        keys.send_text("\x01\x03")  # Ctrl+A, Ctrl+C.
        await until(lambda: system["text"] == text)
        assert ui.app.is_running and not ui._exiting
        assert ui.input.text == text
        system["text"] = "Replacement context"
        keys.send_text("\x16")  # Ctrl+V replaces the selection.
        await until(lambda: ui.input.text == "Replacement context")
        assert ui.app.is_running

    run_ui(check)


def test_shift_selection_copy_and_cut_preserve_unselected_text(monkeypatch):
    system = []
    monkeypatch.setattr(clipboard, "write_text", system.append)

    async def check(ui, keys, terminal):
        keys.send_text("hello world")
        await until(lambda: ui.input.text == "hello world")
        keys.send_text("\x1b[1;2D" * 5)  # Shift+Left selects "world".
        await until(
            lambda: (
                ui.input.buffer.selection_state is not None
                and ui.input.buffer.cursor_position == 6
            )
        )
        keys.send_text("\x03")
        await until(lambda: system == ["world"])
        assert ui.input.text == "hello world"
        keys.send_text("\x18")  # Ctrl+X.
        await until(lambda: ui.input.text == "hello ")
        assert system == ["world", "world"]

    run_ui(check)


@pytest.mark.parametrize("terminal_paste", [False, True])
def test_multiline_paste_preserves_context_without_executing_slash_commands(
    monkeypatch, terminal_paste
):
    pasted = "/logout\r\nsecond line\rthird line"
    monkeypatch.setattr(clipboard, "read_text", lambda: pasted)

    async def check(ui, keys, terminal):
        keys.send_text("old draft\x01")
        await until(lambda: ui.input.buffer.selection_state is not None)
        keys.send_text("\x1b[200~" + pasted + "\x1b[201~" if terminal_paste else "\x16")
        await until(lambda: ui.input.text == "/logout\nsecond line\nthird line")
        assert not ui._account_logout_running
        assert not ui._exiting and ui.app.is_running
        assert ui.session is None

    run_ui(check)


def test_clipboard_failure_keeps_draft_and_selection(monkeypatch):
    def fail(*args):
        raise clipboard.ClipboardError("System clipboard unavailable")

    monkeypatch.setattr(clipboard, "read_text", fail)
    monkeypatch.setattr(clipboard, "write_text", fail)

    async def check(ui, keys, terminal):
        keys.send_text("keep draft\x01\x18")
        await until(lambda: ui._input_notice == "System clipboard unavailable")
        assert ui.input.text == "keep draft"
        assert ui.input.buffer.selection_state is not None
        keys.send_text("\x16")
        await until(lambda: ui.input.buffer.selection_state is not None)
        assert ui.input.text == "keep draft" and ui.app.is_running

    run_ui(check)


def test_system_clipboard_errors_are_reported_without_exposing_contents(monkeypatch):
    def fail(*args):
        raise clipboard.pyperclip.PyperclipException("private platform detail")

    monkeypatch.setattr(clipboard.pyperclip, "copy", fail)
    monkeypatch.setattr(clipboard.pyperclip, "paste", fail)
    with pytest.raises(clipboard.ClipboardError, match="Copy failed") as copied:
        clipboard.write_text("private draft")
    with pytest.raises(clipboard.ClipboardError, match="Paste failed") as pasted:
        clipboard.read_text()
    assert "private" not in str(copied.value)
    assert "private" not in str(pasted.value)
