from wizard.cli.commands import explain
from wizard.cli.models.investigation_request import RequestOptions


def test_explain_cannot_enable_browser_from_urls_or_environment(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(explain, 'stream_events', lambda request: seen.append(request) or iter(()))
    list(explain.explain('dependencies', str(tmp_path), RequestOptions(browser_enabled=True),
                         'explain dependencies at http://localhost:4000'))
    assert seen[0].options.browser_enabled is False


def test_read_only_tui_does_not_probe_or_offer_frontend(monkeypatch):
    from wizard.cli.tui import app
    from types import SimpleNamespace
    monkeypatch.setattr(app, 'suggestion_for', lambda _: (_ for _ in ()).throw(AssertionError('No frontend needed')))
    view = SimpleNamespace(family='explain', repo_path='.', frontend='old', frontend_hint='old')
    app.WizardTUI._find_frontend(view)
    assert view.frontend is None and view.frontend_hint == ''
