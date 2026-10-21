from io import StringIO
from types import SimpleNamespace

from rich.console import Console

from backend.tests.test_architecture_contract import graph
from wizard.cli.display.architecture import offer_upload


def session(family='investigate'):
    return SimpleNamespace(family=family, target=None, intent_text='architecture', status='completed', investigation_id='inv_local')


def setup(monkeypatch):
    from wizard.cli import account_login
    from wizard.cli.runtime_client import architecture
    calls = []
    monkeypatch.setattr(account_login, 'account_origin', lambda: 'https://wizard.test')
    monkeypatch.setattr(architecture, 'prepare', lambda _: graph())
    monkeypatch.setattr(architecture, 'upload', lambda data, *, consent: calls.append(consent) or 'Saved test graph.')
    output = StringIO()
    return calls, output, Console(file=output)


def test_terminal_architecture_requires_explicit_consent(monkeypatch):
    calls, output, console = setup(monkeypatch)
    assert offer_upload(session(), console, confirm=lambda: False) is None
    assert calls == []
    assert offer_upload(session(), console, confirm=lambda: True) is True
    assert calls == [True]
    assert 'Nodes: 2' in output.getvalue()


def test_piped_or_other_commands_never_upload(monkeypatch):
    calls, _, console = setup(monkeypatch)
    assert offer_upload(session(), console) is None
    assert offer_upload(session('explain'), console, confirm=lambda: True) is None
    assert calls == []


def test_terminal_persistence_failure_returns_failure_without_success_url(monkeypatch):
    from wizard.cli.runtime_client import architecture

    _, output, console = setup(monkeypatch)
    def fail(*args, **kwargs):
        raise ValueError('PostgreSQL unavailable')
    monkeypatch.setattr(architecture, 'upload', fail)
    assert offer_upload(session(), console, confirm=lambda: True) is False
    assert 'upload failed' in output.getvalue()
    assert '/investigations/' not in output.getvalue()
