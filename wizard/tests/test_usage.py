from typer.testing import CliRunner

from wizard.cli.display.usage import counter, format_status
from wizard.cli.main import app
from wizard.cli.runtime_client.usage import parse_sse
from wizard.cli.tui.session import TuiSession


def report(current=None):
    return {
        "profile_id": "local",
        "scope": "local-profile",
        "current_run": current,
        "totals": {
            "total_tokens": 40,
            "input_tokens": 30,
            "output_tokens": 10,
            "llm_calls": 4,
        },
        "by_command": {
            command: {
                "total_tokens": 10,
                "input_tokens": 7,
                "output_tokens": 3,
                "llm_calls": 1,
            }
            for command in ("investigate", "verify", "report", "explain")
        },
    }


def test_status_no_usage_previous_runs_and_resumed_sessions():
    empty = report()
    empty["totals"] = {
        "total_tokens": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "llm_calls": 0,
    }
    text = format_status(empty)
    assert "No recorded runs" in text
    assert "Total tokens:   0" in text
    current = {
        "command": "verify",
        "run_id": "r2",
        "session_id": "resumed-session",
        "status": "completed",
        "finished_at": "now",
        "total_tokens": 10,
        "llm_calls": 1,
    }
    text = format_status(report(current))
    assert "Total tokens:   40" in text
    assert "Run tokens:     10" in text
    assert "all sessions" in text
    for command in ("investigate", "verify", "report", "explain"):
        assert f"{command + ':':<16}10" in text


def test_sse_parser_reconnect_and_counter_replaces_totals():
    lines = [
        ": heartbeat",
        "",
        "id: 1",
        "event: usage",
        'data: {"total_tokens": 10}',
        "",
        "id: 2",
        "event: usage",
        'data: {"total_tokens": 15}',
        "",
        "event: complete",
        "data: {}",
        "",
    ]
    events = list(parse_sse(lines))
    assert len(events) == 3
    session = TuiSession("report", None)
    for _, _, payload in events[:2]:
        session._consume({"event_type": "usage.updated", "payload": payload})
    assert session.snapshot()["usage"]["total_tokens"] == 15
    session._consume({"event_type": "usage.updated", "payload": {"total_tokens": 15}})
    assert session.snapshot()["usage"]["total_tokens"] == 15
    assert not session.activity


def test_status_argument_never_starts_commands_planner_or_agents(monkeypatch):
    monkeypatch.setattr("wizard.cli.runtime_client.usage.status", lambda: report())
    result = CliRunner().invoke(app, ["/status"])
    assert result.exit_code == 0, result.output
    assert "Wizard Usage Monitor" in result.output
    assert "Total tokens:   40" in result.output


def test_all_four_arguments_dispatch_existing_commands(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "wizard.cli.display.terminal.run_command",
        lambda family, words, console: calls.append((family, words)) or 0,
    )
    for command in ("investigate", "verify", "report", "explain"):
        args = [command] + ([] if command == "report" else ["architecture"])
        result = CliRunner().invoke(app, args)
        assert result.exit_code == 0, result.output
    assert [c[0] for c in calls] == ["investigate", "verify", "report", "explain"]


def test_counter_labels_unknown_pending_and_final_usage():
    assert "pending" in counter(None)
    assert "incomplete" in counter({"total_tokens": 10, "incomplete": True})
    assert "in progress" in counter({"total_tokens": 10, "pending_requests": 1})
    assert "01:02" in counter({"total_tokens": 10}, 62)


def test_status_in_tui_is_local_and_does_not_start_work(monkeypatch):
    import threading

    from wizard.cli.tui.app import INTENT, WizardTUI

    done = threading.Event()

    def persisted_status():
        done.set()
        return report()

    monkeypatch.setattr("wizard.cli.runtime_client.usage.status", persisted_status)
    from prompt_toolkit.application import create_app_session
    from prompt_toolkit.input import DummyInput
    from prompt_toolkit.output import DummyOutput

    with create_app_session(input=DummyInput(), output=DummyOutput()):
        ui = WizardTUI()
    ui.state = INTENT
    monkeypatch.setattr(
        ui, "_begin_work", lambda *a: (_ for _ in ()).throw(AssertionError("LLM path"))
    )
    ui.input.buffer.text = "/status"
    assert ui._on_accept(ui.input.buffer) is False
    assert done.wait(2)
    assert ui.session is None


def test_standalone_status_starts_only_runtime_after_a_cli_restart(monkeypatch):
    from types import SimpleNamespace

    import httpx

    from wizard.cli.runtime_client import usage

    calls = []

    def status():
        calls.append("read")
        if len(calls) == 1:
            raise httpx.ConnectError("runtime stopped")
        return report()

    class Supervisor:
        def ensure_all(self, specs):
            assert [s.key for s in specs] == ["kernel"]
            calls.append("runtime")
            return SimpleNamespace(kernel_ok=True)

        def stop(self):
            calls.append("stop")

    monkeypatch.setattr(usage, "status", status)
    monkeypatch.setattr("wizard.cli.tui.services.ServiceSupervisor", Supervisor)
    monkeypatch.setattr(
        "wizard.cli.tui.services.build_specs",
        lambda: [
            SimpleNamespace(key="kernel", port=8080),
            SimpleNamespace(key="planner"),
            SimpleNamespace(key="agents"),
        ],
    )
    monkeypatch.setenv("WIZARD_ENGINE_URL", "http://127.0.0.1:8080")
    assert usage.standalone_status()["totals"]["total_tokens"] == 40
    assert calls == ["read", "runtime", "read", "stop"]


def test_database_dotenv_value_is_passed_only_to_runtime(monkeypatch, tmp_path):
    from wizard.cli.tui.services import build_specs

    monkeypatch.delenv("WIZARD_DATABASE_URL", raising=False)
    (tmp_path / ".env").write_text(
        "Wizard_DATABASE_URL=postgresql://fixture\n", encoding="utf-8"
    )
    specs = build_specs(tmp_path)
    assert (
        next(s for s in specs if s.key == "kernel").env["WIZARD_DATABASE_URL"]
        == "postgresql://fixture"
    )
    assert all("WIZARD_DATABASE_URL" not in s.env for s in specs if s.key != "kernel")


def test_dumb_tty_redraws_authoritative_counter_in_place_and_preserves_logs():
    from io import StringIO

    from rich.console import Console
    from rich.text import Text

    from wizard.cli.display.terminal import _TokenLine

    output = StringIO()
    console = Console(
        file=output,
        force_terminal=True,
        no_color=True,
        width=100,
        _environ={"TERM": "dumb"},
    )
    assert console.is_dumb_terminal
    usage = {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15, "llm_calls": 1}

    class Meter:
        def __rich__(self):
            return Text(counter(usage, 8))

    with _TokenLine(console, Meter()) as line:
        line.print("[planner] Building investigation plan...")
        usage.update(input_tokens=30, output_tokens=12, total_tokens=42, llm_calls=2)
        line.refresh()
        # A duplicate persisted snapshot changes neither totals nor terminal output.
        before = output.getvalue()
        line.refresh()
        assert output.getvalue() == before
    text = output.getvalue()
    assert "[planner] Building investigation plan...\n" in text
    assert "\rTokens: 15" in text
    assert "\rTokens: 42" in text
    assert "in 30 / out 12" in text
    assert "LLM calls: 2 | Elapsed: 00:08" in text
    assert "\nTokens:" not in text
    assert "\x1b" not in text


def test_redirected_terminal_does_not_print_live_counter_updates():
    from io import StringIO

    from rich.console import Console
    from rich.text import Text

    from wizard.cli.display.terminal import _TokenLine

    output = StringIO()
    console = Console(file=output, force_terminal=False)

    class Meter:
        def __rich__(self):
            return Text("Tokens: 15")

    with _TokenLine(console, Meter()) as line:
        line.refresh()
        line.print("[agent] Analyzing package entry points...")
    assert output.getvalue() == "[agent] Analyzing package entry points...\n"
def test_supervisor_selects_separate_runtime_venv(monkeypatch, tmp_path):
    from wizard.cli.tui import services
    monkeypatch.setattr(services, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(services, "_python", lambda: "cli-python")
    relative = "Scripts/python.exe" if services.os.name == "nt" else "bin/python"
    engine = tmp_path / "wizard-runtime-engine"
    interpreter = engine / "venv" / relative
    interpreter.parent.mkdir(parents=True)
    interpreter.touch()
    assert services._kernel_python() == str(interpreter)
    preferred = engine / ".venv" / relative
    preferred.parent.mkdir(parents=True)
    preferred.touch()
    assert services._kernel_python() == str(preferred)

