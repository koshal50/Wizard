"""Interactive input, local controls, and bounded shutdown without model calls."""

import threading
import time
from contextlib import contextmanager
from types import SimpleNamespace

from prompt_toolkit.application import create_app_session
from prompt_toolkit.document import Document
from prompt_toolkit.input import DummyInput
from prompt_toolkit.output import DummyOutput

from wizard.cli.parser.command_parser import SLASH_COMMANDS, VALID_COMMANDS
from wizard.cli.tui.app import INTENT, WORKING, WizardTUI
from wizard.cli.tui.session import TuiSession


def test_startup_menu_has_visible_intent_box_before_slash():
    import asyncio

    from prompt_toolkit.application.current import set_app

    with ui() as app:
        assert app.input.text == ""
        assert not app._status_input

        async def render():
            with set_app(app.app):
                app.app.renderer.render(app.app, app.app.layout)
                await app.app.cancel_and_wait_for_background_tasks()

        asyncio.run(render())
        assert app.input.window.render_info is not None
        assert app.input.window.render_info.window_height == 1
        assert app.input_frame.title == "Intent / command"


def test_account_label_is_beside_activity_and_updates_cached_header(monkeypatch):
    from prompt_toolkit.formatted_text import to_formatted_text
    from wizard.cli.tui import widgets

    # Rich's dumb-terminal fallback otherwise ignores the requested test width.
    monkeypatch.setattr(widgets._console, "_height", 40)

    def plain(frame):
        return "".join(fragment[1] for fragment in to_formatted_text(frame))

    with ui() as app:
        app._geometry = lambda: (140, 40)
        before = app._render_top()
        heading = next(line for line in plain(before).splitlines() if "Recent activity" in line)
        assert "(default user)" in heading
        assert heading.index("(default user)") > heading.index("Recent activity")
        app._set_account({"full_name": "Ada Lovelace", "email": "ada@example.test"})
        after = app._render_top()
        assert after is not before
        assert "(Ada Lovelace)" in plain(after)
        assert "default user" not in plain(after)
        assert app._render_top() is after
        app._set_account(None)
        assert "(default user)" in plain(app._render_top())


def test_startup_account_check_cannot_overwrite_new_login(monkeypatch):
    from wizard.cli import account_login

    with ui() as app:
        jobs = []
        monkeypatch.setattr(
            threading, "Thread",
            lambda target, **kwargs: SimpleNamespace(start=lambda: jobs.append(target)),
        )

        class Flow:
            store = SimpleNamespace(load=lambda: {})

            def authenticated_account(self, existing):
                app._set_account({"full_name": "New login"})
                return {"full_name": "Old account"}

            def close(self):
                pass

            def cancelled(self):
                return False

        monkeypatch.setattr(account_login, "LoginFlow", Flow)
        app._load_account_identity()
        jobs[0]()
        assert app._account_name == "New login"


@contextmanager
def ui():
    with create_app_session(input=DummyInput(), output=DummyOutput()):
        yield WizardTUI()


def test_active_input_retains_draft_and_does_not_dispatch(monkeypatch):
    with ui() as app:
        app.state = WORKING
        app.session = TuiSession("investigate", "architecture", running=True)
        app.app.layout.focus(app.input)
        app._status_input = True  # user edited a slash shortcut into a draft
        buffer = app.input.buffer
        buffer.text = "a draft with j k b r q"
        assert not app.input.read_only()
        assert app.app.layout.has_focus(app.input)
        monkeypatch.setattr(
            app, "_begin_work", lambda text: (_ for _ in ()).throw(AssertionError())
        )
        assert app._on_accept(buffer) is True
        assert buffer.text == "a draft with j k b r q"
        assert app.session.running


def test_normal_intent_still_dispatches_once(monkeypatch):
    with ui() as app:
        app.state = INTENT
        calls = []
        monkeypatch.setattr(app, "_begin_work", calls.append)
        app.input.text = "architecture"
        assert app._on_accept(app.input.buffer) is False
        assert calls == ["architecture"]


def test_finishing_keeps_draft_focus_and_restores_report_shortcuts_when_empty(
    monkeypatch,
):
    with ui() as app:
        monkeypatch.setattr(app, "_record_history", lambda snap: None)
        for text in ("draft j k b r q", ""):
            app.state = WORKING
            app.session = TuiSession("investigate", "architecture", finished=True)
            app.input.text = text
            app.app.layout.focus(app.input)
            app._sync_finished()
            assert app.input.text == text
            assert app.app.layout.has_focus(app.input if text else app.body)


def test_inline_completion_uses_actual_registry_without_persistent_help():
    with ui() as app:
        completions = list(
            app.input.completer.get_completions(
                Document("/"), SimpleNamespace(completion_requested=True)
            )
        )
        assert [(item.text, item.display_meta_text) for item in completions] == list(
            SLASH_COMMANDS.items()
        )
        assert not hasattr(app, "_command_help")
        assert app._input_notice == ""
        assert app._current_options() == VALID_COMMANDS
        assert VALID_COMMANDS == ["investigate", "verify", "report", "explain"]


def test_exit_during_blocked_cancellation_is_immediate_and_idempotent(monkeypatch):
    entered, release = threading.Event(), threading.Event()
    calls = []

    def cancel(run):
        calls.append(run)
        entered.set()
        release.wait(2)
        return True

    monkeypatch.setattr("wizard.cli.runtime_client.client.cancel_investigation", cancel)
    with ui() as app:
        app.state = WORKING
        app.session = TuiSession(
            "verify", "runtime", running=True, investigation_id="active"
        )
        exits = []
        monkeypatch.setattr(app.app, "exit", lambda: exits.append(True))
        app.input.text = "/exit"
        try:
            start = time.monotonic()
            app._on_accept(app.input.buffer)
            app._on_accept(app.input.buffer)
            assert time.monotonic() - start < 0.3
            assert entered.wait(1)
            assert exits == [True]
            assert calls == ["active"]
            assert app.session.cancelled
            start = time.monotonic()
            app.session.shutdown(timeout=0.05)
            assert time.monotonic() - start < 0.3
        finally:
            release.set()
            app.session.shutdown(timeout=1)


def test_unknown_slash_is_never_an_llm_intent(monkeypatch):
    with ui() as app:
        app.state = INTENT
        monkeypatch.setattr(
            app, "_begin_work", lambda text: (_ for _ in ()).throw(AssertionError())
        )
        app.input.text = "/unsupported"
        assert app._on_accept(app.input.buffer) is True
        assert "Unknown command" in app._input_notice
        assert app.input.text == "/unsupported"


def test_cancel_stops_and_closes_existing_usage_consumer(monkeypatch):
    closed = []
    monitor = SimpleNamespace(stop=threading.Event(), close=lambda: closed.append(True))
    session = TuiSession(
        "investigate", "architecture", running=True, investigation_id="active"
    )
    session._register_monitor(monitor)
    monkeypatch.setattr(
        "wizard.cli.runtime_client.client.cancel_investigation", lambda run: True
    )
    session.shutdown(timeout=1)
    assert monitor.stop.is_set() and closed == [True]
    assert not session._cancel_thread.is_alive()


def test_windows_cleanup_targets_owned_process_tree(monkeypatch):
    from wizard.cli.tui import services

    calls = []
    process = SimpleNamespace(pid=12345, poll=lambda: None, wait=lambda timeout: None)
    monkeypatch.setattr(services.os, "name", "nt")
    monkeypatch.setattr(
        services.subprocess, "run", lambda args, **kwargs: calls.append((args, kwargs))
    )
    services._terminate(process)
    assert calls[0][0] == ["taskkill", "/T", "/F", "/PID", "12345"]
    assert calls[0][1]["timeout"] == 4


def test_cancel_during_post_acknowledgement_stops_the_new_run(monkeypatch):
    from wizard.cli.runtime_client import client
    monkeypatch.setattr("wizard.cli.runtime_client.account.account_headers", lambda: {})

    stop = threading.Event()
    cancelled = []
    accepted = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            stop.set()  # /exit races runtime acceptance
            return b'{"investigation_id":"accepted-late","usage_enabled":true}'

    monkeypatch.setattr(client, "_api_payload", lambda request: {})
    monkeypatch.setattr(
        client.urllib.request, "urlopen", lambda *args, **kwargs: Response()
    )
    monkeypatch.setattr(client, "cancel_investigation", cancelled.append)
    with client.listen_cancel(stop, lambda monitor: None, accepted.append):
        assert list(client.stream_events(None)) == []
    assert cancelled == ["accepted-late"]
    assert accepted == ["accepted-late"]


def test_windows_shutdown_batches_owned_services_and_leaves_adopted_alone(monkeypatch):
    from wizard.cli.tui import services

    calls = []
    monkeypatch.setattr(services.os, "name", "nt")
    monkeypatch.setattr(
        services,
        "_terminate",
        lambda process, **kwargs: calls.append((process, kwargs)),
    )
    supervisor = services.ServiceSupervisor()
    owned = [
        SimpleNamespace(
            process=SimpleNamespace(poll=lambda: 0), spec=SimpleNamespace(label=name)
        )
        for name in ("runtime", "agents")
    ]
    adopted = SimpleNamespace(process=None, spec=SimpleNamespace(label="planner"))
    supervisor.report = SimpleNamespace(states=owned + [adopted])
    assert supervisor.stop() == ["runtime", "agents"]
    assert len(calls) == 1
    assert calls[0][1]["additional"] == [owned[1].process]
