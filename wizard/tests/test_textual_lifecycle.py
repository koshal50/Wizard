"""Native UI regressions. No services, browser or provider requests."""
import asyncio
import threading
from unittest.mock import patch

import pytest

pytest.importorskip("textual")

from textual.widgets import Input
from wizard.cli.tui.preferences import load_preferences
from wizard.cli.tui.session import TuiSession
from wizard.cli.tui.textual_app import WizardApp
from wizard_kernel.control.flow_trace import execution_preview


def test_full_width_execution_and_separate_report(tmp_path):
    from wizard.cli.tui.textual_app import ReportScreen
    async def check():
        app = WizardApp(tmp_path, preferences_path=tmp_path / "ui.json")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert app.query_one("#content").region.width > 110
            assert not app.query("#run-report")
            app.push_screen(ReportScreen("# Saved verification\n\nActual evidence"))
            await pilot.pause()
            await pilot.click("#close-report")
            await pilot.pause()
            assert not isinstance(app.screen, ReportScreen)
        app.shutdown()
    asyncio.run(check())


def test_intent_bar_stays_anchored_when_reaper_speech_changes(tmp_path):
    from wizard.cli.tui.reaper_widget import ReaperGuide
    async def check():
        app = WizardApp(tmp_path, preferences_path=tmp_path / "ui.json")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            initial = app.query_one("#input-row").region.y
            sprite = app.query_one("#real-reaper").region
            app.query_one("#guide", ReaperGuide).explain("A much longer reply " * 50, immediate=True)
            await pilot.pause()
            assert app.query_one("#input-row").region.y == initial
            assert app.query_one("#real-reaper").region == sprite
            assert initial >= 35
        app.shutdown()
    asyncio.run(check())


def test_execution_follows_later_output_to_end(tmp_path):
    from wizard.cli.tui.live_run import LiveRun
    async def check():
        app = WizardApp(tmp_path, preferences_path=tmp_path / "ui.json")
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause()
            app._finish_intro()
            for selector in ("#families", "#targets", "#help", "#review"):
                app.query_one(selector).display = False
            view = app.query_one(LiveRun)
            view.display = True
            session = TuiSession("investigate", "architecture")
            for index in range(100):
                session._log("Observed source step " + str(index), "wiz.flow")
            view.display_session(session)
            await pilot.pause(.2)
            content = app.query_one("#content")
            assert content.max_scroll_y > 0
            assert content.scroll_y == content.max_scroll_y
            session._log("Later real result", "wiz.flow")
            view.display_session(session)
            await pilot.pause(.2)
            assert content.scroll_y == content.max_scroll_y
            view.stop_activity("Done")
        app.shutdown()
    asyncio.run(check())


def test_ctrl_t_expands_real_captured_output_and_animation_changes(tmp_path):
    from wizard.cli.tui.live_run import LiveRun
    from textual.widgets import Static
    async def check():
        app = WizardApp(tmp_path, preferences_path=tmp_path / "ui.json")
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            app._finish_intro()
            session = TuiSession("verify", "runtime")
            session._log("Starting the application", "wiz.flow")
            from wizard.cli.tui.session import LogLine
            session.activity.append(LogLine("\n".join("captured line " + str(i) for i in range(10)), "wiz.dim", "output"))
            view = app.query_one(LiveRun)
            view.display_session(session)
            assert "5 more lines" in str(view.query_one("#run-flow", Static).render())
            assert "captured line 9" not in str(view.query_one("#run-flow", Static).render())
            await pilot.press("ctrl+t")
            assert view.output_expanded
            assert "captured line 9" in str(view.query_one("#run-flow", Static).render())
            frame = view._frame
            view._paint_activity()
            assert view._frame > frame
            await pilot.press("ctrl+t")
            assert not view.output_expanded
            for selector in ("#families", "#targets", "#help", "#review"):
                app.query_one(selector).display = False
            view.display = True
            await pilot.pause()
            await pilot.click("#run-flow", offset=(5, 6))
            assert view.output_expanded
        app.shutdown()
    asyncio.run(check())


def test_usage_footer_uses_previous_formatter_and_single_execution_flow(tmp_path):
    from wizard.cli.display.usage import counter
    from textual.widgets import Static

    async def check():
        app = WizardApp(tmp_path, preferences_path=tmp_path / "ui.json")
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause()
            app.refresh_usage_footer()
            assert str(app.query_one("#usage-footer", Static).render()) == counter(None, 0, compact=True)
            assert not app.query("#run-usage, #run-details, #observed-page")
        app.shutdown()
    asyncio.run(check())


def test_quit_returns_from_welcome(tmp_path):
    async def check():
        app = WizardApp(tmp_path, preferences_path=tmp_path / "ui.json")
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause()
            assert app._tour_open
            assert not (tmp_path / "output").exists()
            await pilot.click("#quit-action")
        app.shutdown()
        assert app._ui_closing
    asyncio.run(asyncio.wait_for(check(), timeout=5))


def test_tour_skips_on_return_and_motion_is_saved(tmp_path):
    async def check():
        preferences = tmp_path / "ui.json"
        app = WizardApp(tmp_path, preferences_path=preferences)
        async with app.run_test(size=(100, 32)) as pilot:
            await pilot.pause()
            await pilot.click("#tour-skip")
            await pilot.click("#motion-action")
        app.shutdown()
        assert load_preferences(preferences) == {"intro_seen": True, "motion": False}
        second = WizardApp(tmp_path, preferences_path=preferences)
        async with second.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            assert not second._tour_open
            assert not second.motion_enabled
        second.shutdown()
    asyncio.run(check())


def test_quit_cancels_active_session(tmp_path):
    async def check():
        app = WizardApp(tmp_path, preferences_path=tmp_path / "ui.json")
        with patch.object(TuiSession, "_cancel_remote"):
            async with app.run_test(size=(100, 32)) as pilot:
                await pilot.pause()
                app._finish_intro()
                app.session = TuiSession("verify", "runtime")
                await pilot.click("#quit-action")
            app.shutdown()
            assert app.session.snapshot()["cancelled"]
    asyncio.run(asyncio.wait_for(check(), timeout=5))


def test_login_code_clears_and_quit_cancels_worker(tmp_path):
    class LoginWorker:
        def __init__(self, notify):
            self.running = True
            self.cancelled = False
            self.codes = []
        def start(self):
            pass
        def submit(self, code):
            self.codes.append(code)
        def cancel(self):
            self.cancelled = True
            self.running = False
    async def check():
        with patch("wizard.cli.account_login.LoginWorker", LoginWorker):
            app = WizardApp(tmp_path, preferences_path=tmp_path / "ui.json")
            async with app.run_test(size=(100, 32)) as pilot:
                await pilot.pause()
                app._start_login(services_ready=True)
                app._login_message(app._account_operation, "Browser opened. Open this URL manually: private-ticket")
                field = app.query_one("#account-code", Input)
                field.value = "1234-abcd-5678"
                field.focus()
                await pilot.press("enter")
                await pilot.pause()
                assert app._account_login.codes == ["1234ABCD5678"]
                assert not field.value
                await pilot.press("ctrl+q")
            app.shutdown()
            assert app._account_login.cancelled
    asyncio.run(asyncio.wait_for(check(), timeout=5))


def test_real_output_preview_is_redacted_bounded_and_deduplicated():
    preview = execution_preview({"ok": True, "data": {
        "stdout": "password=do-not-show\n" + "x" * 3000,
        "exit_code": 0, "file_content": "not a live output field",
    }})
    assert "do-not-show" not in preview["stdout"]
    assert len(preview["stdout"]) <= 2001
    assert "file_content" not in preview
    session = TuiSession("verify", "runtime")
    event = {"event_type": "tool.observed", "payload": {
        "observation_id": "local-observation", "tool": "execute_command", "ok": True, "result": preview,
    }}
    session._consume(event)
    session._consume(event)
    assert len(session.snapshot()["execution_outputs"]) == 1


def test_default_tui_dispatches_native_without_starting_services(tmp_path, monkeypatch):
    from wizard.cli.tui.app import run_tui
    monkeypatch.delenv("WIZARD_UI", raising=False)
    with patch("wizard.cli.tui.textual_app.run_native") as native:
        run_tui(str(tmp_path))
        native.assert_called_once_with(project=str(tmp_path))


def test_cancelled_service_start_retains_process_for_cleanup(tmp_path):
    from wizard.cli.tui.services import ServiceSpec, ensure_service
    cancel = threading.Event()
    spec = ServiceSpec("local", "Local", 12345, "/health", str(tmp_path), ("unused",))
    process = object()
    def spawn(*_):
        cancel.set()
        return process
    with patch("wizard.cli.tui.services.healthy", return_value=False), patch("wizard.cli.tui.services.port_open", return_value=False), patch("wizard.cli.tui.services._spawn", side_effect=spawn):
        result = ensure_service(spec, tmp_path, cancel_event=cancel)
    assert result.process is process
    assert result.detail == "startup cancelled"


def test_connection_failure_preserves_the_service_reason(tmp_path):
    from wizard.cli.tui.services import ServiceReport, ServiceSpec, ServiceState
    spec = ServiceSpec("kernel", "Runtime Engine", 8080, "/health", str(tmp_path), None)
    report = ServiceReport(states=[ServiceState(spec, "unavailable", "an older Wizard Runtime is already running; stop it and run wizard again")])
    class Supervisor:
        def __init__(self, **kwargs):
            pass
        def ensure_all(self, **kwargs):
            return report
        def stop(self, **kwargs):
            return []
    async def check():
        with patch("wizard.cli.tui.services.ServiceSupervisor", Supervisor):
            app = WizardApp(tmp_path, preferences_path=tmp_path / "ui.json")
            result = []
            async with app.run_test(size=(100, 32)) as pilot:
                app._connect_services(result.append)
                await pilot.pause(.2)
                assert len(result) == 1
                assert "older Wizard Runtime" in result[0]
                assert "stop it and run wizard again" in result[0]
            app.shutdown()
    asyncio.run(check())
