"""Independent conversation, navigation, concurrency, clipboard and transport."""

import threading
from contextlib import contextmanager

import pytest
from prompt_toolkit.application import create_app_session
from prompt_toolkit.input import DummyInput
from prompt_toolkit.output import DummyOutput

from wizard.cli.tui.app import MENU, RESULT, WORKING, WizardTUI
from wizard.cli.tui.session import TuiSession
from wizard.cli.tui.side_chat import SideChat, request_reply


@contextmanager
def ui():
    with create_app_session(input=DummyInput(), output=DummyOutput()):
        app = WizardTUI()
        yield app
        if app.side_chat:
            app.side_chat.close()


def enter(app, text):
    app.input.text = text
    return app._on_accept(app.input.buffer)


def wait(chat):
    chat.worker.join(2)
    assert not chat.worker.is_alive()


def test_direct_open_and_navigation_does_not_invent_parent():
    with ui() as app:
        enter(app, "/btw")
        identity = app.side_chat.id
        assert app.show_btw and app.session is None and app.state == MENU
        assert app.input_frame.title == "/btw conversation"
        for _ in range(4):
            enter(app, "/btw main")
            assert not app.show_btw and app.state == MENU
            enter(app, "/btw return")
            assert app.side_chat.id == identity
        assert not app.side_chat.messages and app.side_chat.worker is None
        assert "Navigate to main chat" in app._render_body().value


def test_parent_continues_and_completion_is_real_while_side_response_pending(monkeypatch):
    gate = threading.Event()
    calls = []
    def reply(*args):
        calls.append(args)
        assert gate.wait(2)
        return "git branch --show-current"
    with ui() as app:
        parent = TuiSession("investigate", "architecture", running=True)
        app.state, app.session = WORKING, parent
        monkeypatch.setattr(app, "_record_history", lambda snap: None)
        enter(app, "/btw")
        app.side_chat.responder = reply
        enter(app, "Give only the branch command")
        assert app.side_chat.pending and parent.running
        for _ in range(3):
            enter(app, "/btw main")
            assert app.session is parent and app.state == WORKING and parent.running
            enter(app, "/btw return")
        # Existing parent event consumer continues independently of chat.
        parent._consume({"event_type": "engine_unavailable", "error": "test failure"})
        app._sync_finished()
        assert app.state == RESULT and app.show_btw
        gate.set()
        wait(app.side_chat)
        enter(app, "/btw main")
        assert app.session is parent and app.state == RESULT
        enter(app, "/btw return")
        assert app.side_chat.messages[-1]["content"] == "git branch --show-current"
        assert len(calls) == 1
        assert "Give only" not in str(parent.snapshot())


def test_followups_retain_only_chat_transcript_and_create_no_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    calls = []
    def reply(cid, sid, messages):
        calls.append((cid, sid, messages))
        return "answer " + str(len(calls))
    chat = SideChat(lambda: None, responder=reply)
    for question in ["question", "Continue explaining the previous answer"]:
        assert chat.submit(question)
        wait(chat)
    assert calls[0][0] == calls[1][0] == chat.id
    assert calls[1][2] == [
        {"role": "user", "content": "question"},
        {"role": "assistant", "content": "answer 1"},
        {"role": "user", "content": "Continue explaining the previous answer"}]
    assert list(tmp_path.iterdir()) == []


def test_pending_submission_retains_draft_and_empty_is_not_sent():
    gate = threading.Event()
    with ui() as app:
        enter(app, "/btw")
        app.side_chat.responder = lambda *args: gate.wait(2) and "done"
        assert enter(app, "   ")
        assert not app.side_chat.messages
        enter(app, "first")
        assert enter(app, "second")
        assert app.input.text == "second" and len(app.side_chat.messages) == 1
        enter(app, "/btw new")
        assert "Wait" in app._input_notice
        gate.set()
        wait(app.side_chat)


def test_drafts_and_transcript_survive_switching():
    with ui() as app:
        app.input.text = "parent draft"
        app._navigate_btw(True)
        app.input.text = "chat draft"
        app._navigate_btw(False)
        assert app.input.text == "parent draft"
        app._navigate_btw(True)
        assert app.input.text == "chat draft"
        app._back()
        assert not app.show_btw and app.state == MENU


@pytest.mark.parametrize("answer", ["", None, TimeoutError("timeout")])
def test_provider_failure_and_empty_response_can_recover(answer):
    def fail(*args):
        if isinstance(answer, Exception):
            raise answer
        return answer
    chat = SideChat(lambda: None, responder=fail)
    chat.submit("question")
    wait(chat)
    assert chat.error and not chat.pending
    assert len(chat.messages) == 1
    chat.responder = lambda *args: "recovered"
    chat.submit("try again")
    wait(chat)
    assert chat.messages[-1]["content"] == "recovered" and not chat.error


def test_shutdown_ignores_late_reply_and_does_not_cancel_parent(monkeypatch):
    gate = threading.Event()
    with ui() as app:
        parent = TuiSession("verify", "runtime", running=True)
        app.session = parent
        cancelled = []
        monkeypatch.setattr(parent, "cancel", lambda: cancelled.append(True))
        monkeypatch.setattr(app.app, "exit", lambda: None)
        enter(app, "/btw")
        app.side_chat.responder = lambda *args: gate.wait(2) and "late"
        enter(app, "question")
        enter(app, "/exit")
        gate.set()
        wait(app.side_chat)
        assert cancelled == [True] and app._exiting
        assert len(app.side_chat.messages) == 1


@pytest.mark.parametrize("text", ["24/10/24", "/usr/local/bin", "https://example.com/api", "a / b", "/btwhatever"])
def test_slashes_are_ordinary_conversation_text(text):
    with ui() as app:
        enter(app, "/btw")
        app.side_chat.responder = lambda *args: "answer"
        enter(app, text)
        wait(app.side_chat)
        assert app.side_chat.messages[0]["content"] == text


def test_copy_exact_answer_and_transcript(monkeypatch):
    copied = []
    monkeypatch.setattr("wizard.cli.tui.clipboard.write_text", copied.append)
    with ui() as app:
        enter(app, "/btw")
        app.side_chat.responder = lambda *args: "```sh\ngit status\n```"
        enter(app, "command")
        wait(app.side_chat)
        enter(app, "/btw copy")
        assert copied == ["```sh\ngit status\n```"]
        enter(app, "/btw copy all")
        assert "user:\ncommand" in copied[-1]
        old = app.side_chat
        enter(app, "/btw new")
        assert old.closed and app.side_chat.id != old.id and not app.side_chat.messages


def test_copy_actions_only_visible_and_active_in_side_chat(monkeypatch):
    copied = []
    monkeypatch.setattr("wizard.cli.tui.clipboard.write_text", copied.append)
    with ui() as app:
        assert not any("copy" in key for key in app.input.completer.commands)
        assert "/btw return" not in app.input.completer.commands
        enter(app, "/btw")
        assert "/btw copy" in app.input.completer.commands
        assert "/btw copy all" in app.input.completer.commands
        from prompt_toolkit.completion import CompleteEvent
        from prompt_toolkit.document import Document
        assert [c.text for c in app.input.completer.get_completions(Document("/btw c"), CompleteEvent())] == ["/btw copy", "/btw copy all"]
        app.side_chat.responder = lambda *args: "answer"
        enter(app, "question")
        wait(app.side_chat)
        enter(app, "/btw main")
        assert not any("copy" in key for key in app.input.completer.commands)
        assert "/btw return" in app.input.completer.commands
        enter(app, "/btw copy")
        assert not copied
        assert "Copy answer" not in app._render_body().value
        enter(app, "/btw return")
        enter(app, "/btw copy")
        assert copied == ["answer"]


def test_status_overlay_returns_to_editable_side_conversation():
    with ui() as app:
        enter(app, "/btw")
        app._usage_report = "status"
        app.app.layout.focus(app.body)
        app._back()
        assert app.show_btw and app.app.layout.has_focus(app.input)
        assert app._status_input and app._usage_report is None


def test_response_finishes_while_showing_main_and_returns_without_repeat():
    gate = threading.Event()
    calls = []
    def reply(*args):
        calls.append(True)
        assert gate.wait(2)
        return "completed while away"
    with ui() as app:
        enter(app, "/btw")
        app.side_chat.responder = reply
        enter(app, "question")
        enter(app, "/btw main")
        gate.set()
        wait(app.side_chat)
        assert not app.show_btw
        enter(app, "/btw return")
        assert "completed while away" in app._render_body().value
        assert calls == [True] and len(app.side_chat.messages) == 2


def test_transport_identity_and_payload(monkeypatch):
    import httpx
    seen = []
    def handle(request):
        import json
        seen.append(json.loads(request.content))
        assert request.url.path == "/v1/btw"
        return httpx.Response(200, json={"conversation_id": "chat", "text": "answer"})
    real = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: real(transport=httpx.MockTransport(handle)))
    assert request_reply("chat", "session", [{"role": "user", "content": "question"}]) == "answer"
    assert seen[0]["conversation_id"] == "chat"


@pytest.mark.parametrize("shortcut", ["\x1b[17~", "\x1bb"])
def test_real_tui_input_navigation_and_copy_menu(monkeypatch, shortcut):
    import asyncio

    from prompt_toolkit.input import create_pipe_input

    monkeypatch.setattr("wizard.cli.tui.side_chat.request_reply", lambda *args: "response ready")
    async def until(predicate):
        for _ in range(200):
            if predicate():
                return
            await asyncio.sleep(0.01)
        raise AssertionError("TUI did not update")

    async def run():
        with create_pipe_input() as keys, create_app_session(input=keys, output=DummyOutput()):
            app = WizardTUI()
            parent = TuiSession("verify", "runtime", running=True)
            app.state, app.session = WORKING, parent
            task = asyncio.create_task(app.app.run_async())
            try:
                await until(lambda: app.app.is_running)
                app.app.layout.focus(app.input)
                keys.send_text("/btw only answer my question\r")
                await until(lambda: app.side_chat and len(app.side_chat.snapshot()["messages"]) == 2)
                assert app.show_btw and parent.running
                app.input.text = "side draft"
                keys.send_text(shortcut)
                await until(lambda: not app.show_btw)
                assert parent.running and app.session is parent
                app.input.text = "parent draft"
                keys.send_text(shortcut)
                await until(lambda: app.show_btw)
                assert app.input.text == "side draft"
                keys.send_text(shortcut)
                await until(lambda: not app.show_btw)
                assert app.input.text == "parent draft"
                app.input.text = ""
                keys.send_text("/")
                await until(lambda: app.slash_menu.visible)
                assert not any("copy" in entry.text for entry in app.slash_menu.entries)
                app.input.text = ""
                keys.send_text("/btw return\r")
                await until(lambda: app.show_btw)
                assert app.input.text == "side draft"
                app.input.text = ""
                keys.send_text("/btw c")
                await until(lambda: len(app.slash_menu.entries) == 2)
                assert all("copy" in entry.text for entry in app.slash_menu.entries)
                assert len(app.side_chat.messages) == 2
            finally:
                if app.side_chat:
                    app.side_chat.close()
                app.app.exit()
                await task
    asyncio.run(run())
