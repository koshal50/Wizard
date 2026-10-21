"""Logout outcomes, secure deletion, process ordering, and live label races."""

import io
import subprocess
import sys
from types import SimpleNamespace

import httpx
import pytest
from prompt_toolkit.application import create_app_session
from prompt_toolkit.input import DummyInput
from prompt_toolkit.output import DummyOutput
from rich.console import Console

from wizard.cli import account_logout
from wizard.cli.account_session import current_generation
from wizard.cli.account_storage import CredentialStore, StorageError
from wizard.cli.tui.app import WizardTUI

ORIGIN = "https://accounts.example.test"


class Store:
    def __init__(self, value=None):
        self.value = value
        self.fail = False

    def load(self):
        return self.value

    def delete(self):
        if self.fail:
            raise StorageError("Secure credential removal failed")
        self.value = None


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("success", account_logout.LOGGED_OUT),
        ("revoked", account_logout.LOGGED_OUT),
        ("offline", account_logout.LOCAL_ONLY),
        ("server_error", account_logout.LOCAL_ONLY),
        ("malformed", account_logout.LOCAL_ONLY),
    ],
)
def test_logout_removes_locally_then_revokes_only_cli_credential(mode, expected):
    store = Store({"access_token": "test-token"})
    removed = []
    requests = []

    def transport(request):
        assert store.value is None
        assert removed == [True]
        assert request.method == "DELETE"
        assert request.url.path == "/api/account/credential"
        assert request.headers["authorization"] == "Bearer test-token"
        assert "cookie" not in request.headers
        requests.append(request)
        if mode == "offline":
            raise httpx.ConnectError("offline")
        if mode == "malformed":
            return httpx.Response(200, json={"revoked": False})
        status = {"revoked": 401, "server_error": 503}.get(mode, 200)
        return httpx.Response(status, json={"revoked": True})

    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        assert (
            account_logout.logout(ORIGIN, store, client, lambda: removed.append(True))
            == expected
        )
        assert store.value is None
        assert (
            account_logout.logout(ORIGIN, store, client) == account_logout.ALREADY_OUT
        )
    assert len(requests) == 1


def test_removal_failure_never_reports_success_or_changes_identity():
    store = Store({"access_token": "keep-on-failure"})
    store.fail = True
    previous = current_generation(store)
    with pytest.raises(StorageError, match="removal failed"):
        account_logout.logout(
            ORIGIN, store, on_removed=lambda: pytest.fail("Claimed removal")
        )
    assert store.value is not None
    assert current_generation(store) != previous


@pytest.mark.parametrize("offline", [False, True])
def test_logout_cancels_securely_registered_pending_login_without_browser_logout(
    offline,
):
    pending = Store({"request": {"request_id": "request", "verifier": "secret-proof"}})
    store = Store()
    store.pending_store = lambda: pending
    paths = []

    def transport(request):
        paths.append(request.url.path)
        assert pending.value is None
        if offline:
            raise httpx.ConnectError("offline")
        return httpx.Response(200, json={"state": "cancelled"})

    with httpx.Client(transport=httpx.MockTransport(transport)) as client:
        result = account_logout.logout(ORIGIN, store, client)
    assert result == (
        account_logout.LOCAL_ONLY if offline else account_logout.LOGGED_OUT
    )
    assert paths == ["/api/cli/cancel"]
    assert store.value is None


def test_terminal_logout_failure_returns_nonzero(monkeypatch):
    def fail():
        raise StorageError("Secure credential removal failed")

    monkeypatch.setattr(account_logout, "logout", fail)
    output = io.StringIO()
    assert account_logout.terminal_logout(Console(file=output)) == 1
    assert "Logout failed." in output.getvalue()
    assert account_logout.LOGGED_OUT not in output.getvalue()


def test_logout_is_available_at_standalone_login_code_prompt(monkeypatch):
    import threading

    from wizard.cli import account_login

    closed = []

    class Flow:
        active = True
        complete = False
        cancel_event = threading.Event()

        def start(self):
            return "Open the website"

        def close(self, cancel=False):
            closed.append(cancel)

    monkeypatch.setattr(account_login, "LoginFlow", Flow)
    monkeypatch.setattr("builtins.input", lambda prompt: "/logout")
    monkeypatch.setattr(account_logout, "terminal_logout", lambda console: 0)
    assert account_login.terminal_login(Console(file=io.StringIO())) == 0
    assert Flow.cancel_event.is_set()
    assert closed == [True]


def test_cross_process_logout_generation_invalidates_previous_login(tmp_path):
    store = CredentialStore(ORIGIN)
    store.path = tmp_path / "isolated.json"
    previous = current_generation(store)
    code = (
        "from pathlib import Path; from wizard.cli.account_storage import CredentialStore; "
        "from wizard.cli.account_session import session_guard,generation; "
        "import sys; s=CredentialStore('https://isolated.invalid'); s.path=Path(sys.argv[1]); "
        "\nwith session_guard(s) as stream: generation(s,stream,advance=True)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code, str(store.path)],
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode()
    assert current_generation(store) != previous


def test_tui_logout_cancels_worker_and_ignores_late_authentication(monkeypatch):
    jobs, workers = [], []

    class Worker:
        running = True

        def __init__(self, notify):
            self.notify = notify
            self.cancelled = False
            workers.append(self)

        def start(self):
            pass

        def cancel(self):
            self.cancelled = True

    monkeypatch.setattr("wizard.cli.account_login.LoginWorker", Worker)
    monkeypatch.setattr(
        "threading.Thread",
        lambda target, **kwargs: SimpleNamespace(start=lambda: jobs.append(target)),
    )

    def logout(on_removed):
        on_removed()
        return account_logout.LOGGED_OUT

    monkeypatch.setattr(account_logout, "logout", logout)
    with create_app_session(input=DummyInput(), output=DummyOutput()):
        ui = WizardTUI()
        ui._set_account({"full_name": "Current user"})
        ui._start_account_login()
        old = workers[0]
        ui.input.text = "/logout"
        assert ui._on_accept(ui.input.buffer) is False
        assert ui.input.text == ""
        assert old.cancelled
        jobs.pop()()
        old.on_authenticated({"full_name": "Stale login"})
        old.notify("connected and verified")
        assert ui._account_name == "default user"
        assert ui._input_notice == account_logout.LOGGED_OUT
        assert ui._usage_report is None


def test_tui_logout_ignores_identity_check_that_finishes_later(monkeypatch):
    jobs = []
    monkeypatch.setattr(
        "threading.Thread",
        lambda target, **kwargs: SimpleNamespace(start=lambda: jobs.append(target)),
    )
    with create_app_session(input=DummyInput(), output=DummyOutput()):
        ui = WizardTUI()

        class Flow:
            store = SimpleNamespace(load=dict)

            def authenticated_account(self, existing):
                ui._start_account_logout()
                jobs.pop()()  # Complete removal before the old identity call returns.
                return {"id": "old", "full_name": "Old identity"}

            def close(self):
                pass

            def cancelled(self):
                return True

        def logout(on_removed):
            on_removed()
            return account_logout.LOGGED_OUT

        monkeypatch.setattr("wizard.cli.account_login.LoginFlow", Flow)
        monkeypatch.setattr(account_logout, "logout", logout)
        ui._load_account_identity()
        jobs.pop()()
        assert ui._account_name == "default user"
        assert ui._account_id is None


def test_tui_keeps_identity_and_reports_failed_secure_removal(monkeypatch):
    monkeypatch.setattr(
        "threading.Thread", lambda target, **kwargs: SimpleNamespace(start=target)
    )

    def fail(**kwargs):
        raise StorageError("Secure credential removal failed")

    monkeypatch.setattr(account_logout, "logout", fail)
    with create_app_session(input=DummyInput(), output=DummyOutput()):
        ui = WizardTUI()
        ui._set_account({"id": "existing", "full_name": "Existing account"})
        ui._start_account_logout()
        assert ui._account_name == "Existing account"
        assert ui._input_notice == "Logout failed. Secure credential removal failed"
        assert not ui._account_logout_running


def test_account_switch_never_labels_previous_runs_tokens_as_new_accounts_usage():
    from wizard.cli.tui.session import TuiSession

    with create_app_session(input=DummyInput(), output=DummyOutput()):
        ui = WizardTUI()
        ui.session = TuiSession("verify", "runtime")
        ui.session.usage = {"profile_id": "account:first", "total_tokens": 35}
        ui._set_account({"id": "second", "full_name": "Second account"})
        footer = "".join(text for _, text in ui._render_usage())
        assert "35" not in footer
        assert "/status" in footer
        assert ui.session.usage["total_tokens"] == 35  # History is retained.
        ui._set_account({"id": "first", "full_name": "First account"})
        assert "35" in "".join(text for _, text in ui._render_usage())


def test_delete_is_idempotent_in_isolated_native_store():
    import os
    from uuid import uuid4

    if os.name != "nt":
        pytest.skip("Native Windows storage test")
    store = CredentialStore("https://logout-" + uuid4().hex + ".invalid")
    saved = False
    try:
        try:
            store.save({"access_token": "isolated-test"})
            saved = True
        except StorageError:
            import ctypes

            if ctypes.get_last_error() == 1312:
                pytest.skip("Windows Credential Manager unavailable in sandbox")
            raise
        store.delete()
        assert store.load() is None
        store.delete()
    finally:
        if saved:
            store.delete()
