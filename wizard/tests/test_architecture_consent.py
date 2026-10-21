import time

from backend.tests.test_architecture_contract import graph
from wizard.cli.tui.app import RESULT
from wizard.tests.test_tui_controls import ui


def wait_for(predicate):
    until = time.monotonic() + 2
    while time.monotonic() < until:
        if predicate():
            return
        time.sleep(.01)
    assert predicate()


def test_declining_consent_never_uploads(monkeypatch):
    from wizard.cli import account_login
    from wizard.cli.runtime_client import architecture
    monkeypatch.setattr(architecture, "prepare", lambda _: graph())
    monkeypatch.setattr(account_login, "account_origin", lambda: "https://wizard.test")
    calls = []
    monkeypatch.setattr(architecture, "upload", lambda *args, **kw: calls.append((args, kw)))
    with ui() as view:
        from types import SimpleNamespace
        session = view.session = SimpleNamespace(investigation_id="inv_test")
        view.state = RESULT
        view._prepare_diagram(session)
        wait_for(lambda: getattr(view, "_diagram", None))
        assert "Type yes to consent" in view._diagram[2]
        assert calls == []
        assert view._answer_diagram("no")
        assert calls == [] and view._diagram[1] is None
        assert "local" in view._diagram[2]


def test_explicit_yes_uploads_once_and_shows_failure_without_url(monkeypatch):
    from wizard.cli import account_login
    from wizard.cli.runtime_client import architecture
    monkeypatch.setattr(account_login, "account_origin", lambda: "https://wizard.test")
    calls = []
    def fail(data, *, consent):
        calls.append((data, consent))
        raise ValueError("PostgreSQL unavailable")
    monkeypatch.setattr(architecture, "upload", fail)
    with ui() as view:
        view.session = object()
        view._diagram = (view.session, graph(), "Consent summary", "https://wizard.test")
        assert not view._answer_diagram("please")
        assert calls == []
        assert view._answer_diagram("yes")
        wait_for(lambda: "upload failed" in view._diagram[2])
        assert len(calls) == 1 and calls[0][1] is True
        assert "saved successfully" not in view._diagram[2] and "/investigations/" not in view._diagram[2]
        assert not view._answer_diagram("yes")


def test_failed_local_coverage_offers_available_graph_as_incomplete(monkeypatch):
    from types import SimpleNamespace

    from wizard.cli import account_login
    from wizard.cli.runtime_client import architecture
    from wizard.cli.tui.app import WORKING

    partial = graph()
    partial["status"] = "incomplete"
    monkeypatch.setattr(architecture, "prepare", lambda _: partial)
    monkeypatch.setattr(account_login, "account_origin", lambda: "https://wizard.test")
    with ui() as view:
        view.session = SimpleNamespace(family="investigate", target="architecture", intent_text="",
            investigation_id="inv_partial", snapshot=lambda: {"finished": True, "status": "failed"})
        view.state = WORKING
        view._record_history = lambda _: None
        view._sync_finished()
        wait_for(lambda: getattr(view, "_diagram", None))
        assert "Graph status: incomplete" in view._diagram[2]
        assert view.session.snapshot()["status"] == "failed"
        assert view._answer_diagram("no")
