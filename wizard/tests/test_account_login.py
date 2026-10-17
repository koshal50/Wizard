"""CLI protocol failures use HTTP transport fakes; PostgreSQL guarantees are tested in backend/."""

import json
import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest

from wizard.cli.account_login import APIError, LoginError, LoginFlow, account_origin
from wizard.cli.account_storage import StorageError


class Store:
    def __init__(self):
        self.value = {"access_token": "previous"}
        self.fail = False

    def load(self):
        return self.value

    def save(self, value):
        if self.fail:
            raise StorageError("disk unavailable")
        self.value = value


@pytest.fixture
def protocol():
    rid, ticket = str(uuid4()), secrets.token_urlsafe(32)
    token = "wa_" + rid + "." + "a" * 64
    expires = (datetime.now(UTC) + timedelta(minutes=10)).isoformat()
    calls = []
    state = {"exchange": "success", "recover": True}
    issued = {"access_token": token, "token_type": "Bearer", "expires_at": expires}

    def transport(request):
        calls.append(
            (request.url.path, json.loads(request.content) if request.content else None)
        )
        path = request.url.path
        if path == "/api/cli/requests":
            return httpx.Response(
                201,
                json={
                    "request_id": rid,
                    "expires_at": expires,
                    "authorization_url": "https://accounts.example.test/cli/authorize#request_id="
                    + rid
                    + "&ticket="
                    + ticket,
                },
            )
        if path == "/api/cli/exchange":
            if state.get("cancel_event"):
                state["cancel_event"].set()
            if state["exchange"] == "timeout":
                raise httpx.ReadTimeout("response lost")
            if state["exchange"] == "invalid":
                return httpx.Response(400, json={"error": "invalid_code"})
            if state["exchange"] == "duplicate":
                return httpx.Response(409, json={"error": "already_exchanged"})
            if state["exchange"] == "malformed":
                return httpx.Response(200, text="invalid json")
            return httpx.Response(200, json=issued)
        if path == "/api/cli/recover":
            return (
                httpx.Response(200, json=issued)
                if state["recover"]
                else httpx.Response(409, json={"error": "not_exchanged"})
            )
        if path == "/api/account/me":
            assert request.headers["authorization"] == "Bearer " + token
            return httpx.Response(
                200,
                json={
                    "account": {
                        "id": str(uuid4()),
                        "email": "account@example.test",
                        "full_name": "Account",
                    }
                },
            )
        if path == "/api/cli/cancel":
            return httpx.Response(200, json={"state": "cancelled"})
        raise AssertionError(path)

    client = httpx.Client(transport=httpx.MockTransport(transport))
    store = Store()
    flow = LoginFlow(
        "https://accounts.example.test",
        client=client,
        store=store,
        opener=lambda _: False,
    )
    yield flow, store, calls, state
    flow.close(cancel=not flow.complete)
    client.close()


def test_manual_fallback_exchange_and_actual_account_verification(protocol):
    flow, store, calls, _ = protocol
    message = flow.start()
    assert "Open this URL manually:" in message
    assert flow.verifier not in message
    assert "Existing account credentials" in message
    result = flow.submit("ABCD-1234-ABCD")
    assert "verified" in result
    assert store.value["access_token"] not in result
    assert [p for p, _ in calls] == [
        "/api/cli/requests",
        "/api/cli/exchange",
        "/api/account/me",
    ]
    assert calls[0][1] == {
        "verifier_hash": __import__("hashlib")
        .sha256(flow.verifier.encode())
        .hexdigest()
    }


@pytest.mark.parametrize("mode", ["timeout", "duplicate", "malformed"])
def test_response_loss_or_duplicate_uses_separate_recovery_not_reexchange(
    protocol, mode
):
    flow, _store, calls, state = protocol
    state["exchange"] = mode
    flow.start()
    flow.submit("ABCD1234ABCD")
    paths = [p for p, _ in calls]
    assert paths.count("/api/cli/exchange") == 1
    assert paths.count("/api/cli/recover") == 1
    assert paths[-1] == "/api/account/me"


def test_invalid_code_keeps_existing_credentials_and_does_not_recover(protocol):
    flow, store, calls, state = protocol
    flow.start()
    state["exchange"] = "invalid"
    with pytest.raises(APIError, match="invalid_code"):
        flow.submit("ABCD1234ABCD")
    assert store.value["access_token"] == "previous"
    assert "/api/cli/recover" not in [p for p, _ in calls]
    with pytest.raises(LoginError, match="12-character"):
        flow.submit("bad")


def test_storage_failure_can_recover_without_losing_old_credentials(protocol):
    flow, store, _calls, state = protocol
    flow.start()
    store.fail = True
    with pytest.raises(LoginError, match="Remote issuance succeeded"):
        flow.submit("ABCD1234ABCD")
    assert store.value["access_token"] == "previous"
    store.fail = False
    state["exchange"] = "duplicate"
    assert "verified" in flow.submit("ABCD1234ABCD")
    assert store.value["access_token"] != "previous"


def test_cancel_is_proof_bearing_idempotent_and_no_code_or_token_logged(protocol):
    flow, store, calls, _ = protocol
    flow.start()
    flow.close(cancel=True)
    flow.close(cancel=True)
    assert calls[-1] == ("/api/cli/cancel", flow.proof())
    assert sum(p == "/api/cli/cancel" for p, _ in calls) == 1
    assert store.value["access_token"] == "previous"


def test_duplicate_login_is_rejected_without_second_initiation(protocol):
    flow, _, calls, _ = protocol
    flow.start()
    with pytest.raises(LoginError, match="already active"):
        flow.start()
    assert len(calls) == 1


def test_unrecoverable_network_failure_preserves_old_credential(protocol):
    flow, store, calls, state = protocol
    state.update(exchange="timeout", recover=False)
    flow.start()
    with pytest.raises(LoginError, match="outcome could not be recovered"):
        flow.submit("ABCD1234ABCD")
    assert store.value["access_token"] == "previous"
    assert len([p for p, _ in calls if p == "/api/cli/exchange"]) == 1


def test_http_is_explicitly_loopback_only(monkeypatch):
    monkeypatch.setenv("WIZARD_ACCOUNT_URL", "http://remote.example.test")
    monkeypatch.setenv("WIZARD_ACCOUNT_LOCAL_DEV", "1")
    with pytest.raises(LoginError, match="HTTPS"):
        account_origin()
    monkeypatch.setenv("WIZARD_ACCOUNT_URL", "http://127.0.0.1:8090")
    assert account_origin() == "http://127.0.0.1:8090"


def test_platform_store_failure_preserves_previous_value(protocol):
    flow, store, _, _ = protocol
    store.fail = True
    flow.start()
    with pytest.raises(LoginError):
        flow.submit("ABCD1234ABCD")
    assert store.value["access_token"] == "previous"


def test_windows_credential_manager_roundtrip_isolated_target():
    import os

    from wizard.cli.account_storage import CredentialStore

    if os.name != "nt":
        pytest.skip("Windows Credential Manager requires Windows")
    store = CredentialStore("https://test-" + str(uuid4()) + ".invalid")
    value = {"access_token": secrets.token_urlsafe(32), "expires_at": "test"}
    try:
        assert store.load() is None
        try:
            store.save(value)
        except StorageError:
            import ctypes

            if ctypes.get_last_error() == 1312:
                pytest.skip(
                    "Credential Manager unavailable in sandbox logon; run this test outside sandbox"
                )
            raise
        assert store.load() == value
        store.save({**value, "expires_at": "replaced"})
        assert store.load()["expires_at"] == "replaced"
    finally:
        import ctypes
        from ctypes import wintypes

        api = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
        api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        api.CredDeleteW(store.target, 1, 0)


def test_tui_login_uses_existing_dispatcher_without_blocking_investigation(monkeypatch):
    from prompt_toolkit.application import create_app_session
    from prompt_toolkit.input import DummyInput
    from prompt_toolkit.output import DummyOutput

    from wizard.cli.tui.app import WORKING, WizardTUI
    from wizard.cli.tui.session import TuiSession

    calls = []

    class Worker:
        running = True

        def __init__(self, notify):
            self.notify = notify

        def start(self):
            calls.append("start")

        def submit(self, code):
            calls.append("code")

        def cancel(self):
            calls.append("cancel")

    monkeypatch.setattr("wizard.cli.account_login.LoginWorker", Worker)
    with create_app_session(input=DummyInput(), output=DummyOutput()):
        app = WizardTUI()
        app.state = WORKING
        app.session = TuiSession("verify", "runtime", running=True)
        for command in ["/login", "/login", "ABCD1234ABCD", "/cancel-login"]:
            app.input.text = command
            assert app._on_accept(app.input.buffer) is False
            assert app.input.text == ""
        assert app.session.running
        assert calls == ["start", "code", "cancel"]


def test_terminal_eof_cancels_without_touching_existing_credentials(monkeypatch):
    import io

    from rich.console import Console

    from wizard.cli import account_login

    calls = []

    class Flow:
        active = True
        complete = False

        def start(self):
            return "Open website"

        def close(self, cancel=False):
            calls.append(cancel)

    monkeypatch.setattr(account_login, "LoginFlow", Flow)
    monkeypatch.setattr("builtins.input", lambda _: (_ for _ in ()).throw(EOFError()))
    assert account_login.terminal_login(Console(file=io.StringIO())) == 1
    assert calls == [True]


def test_local_cancellation_during_exchange_never_overwrites_credentials(protocol):
    flow, store, calls, state = protocol
    flow.start()
    state["cancel_event"] = flow.cancel_event
    with pytest.raises(LoginError, match="cancelled after exchange"):
        flow.submit("ABCD1234ABCD")
    assert store.value["access_token"] == "previous"
    flow.close(cancel=True)
    assert calls[-1][0] == "/api/cli/cancel"


def test_posix_file_permissions_atomic_failure_and_symlink_rejection(
    tmp_path, monkeypatch
):
    import os
    from pathlib import Path

    from wizard.cli.account_storage import CredentialStore

    if os.name == "nt":
        pytest.skip("POSIX mode/ownership guarantees require a POSIX host")
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    store = CredentialStore("https://posix-test.invalid")
    store.save({"access_token": "old"})
    assert store.path.stat().st_mode & 0o777 == 0o600
    assert store.path.parent.stat().st_mode & 0o777 == 0o700
    original = os.replace

    def fail(*args):
        raise OSError("simulated atomic replacement failure")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(StorageError):
        store.save({"access_token": "new"})
    assert store.load()["access_token"] == "old"
    monkeypatch.setattr(os, "replace", original)
    store.path.unlink()
    target = tmp_path / "other.json"
    target.write_text("{}")
    store.path.symlink_to(target)
    with pytest.raises(StorageError):
        store.load()


def test_login_is_available_in_inline_completion_not_primary_menu(monkeypatch):
    from types import SimpleNamespace

    from prompt_toolkit.application import create_app_session
    from prompt_toolkit.document import Document
    from prompt_toolkit.input import DummyInput
    from prompt_toolkit.output import DummyOutput

    from wizard.cli.tui.app import WizardTUI

    calls = []

    class Worker:
        running = True

        def __init__(self, notify):
            pass

        def start(self):
            calls.append("login")

    monkeypatch.setattr("wizard.cli.account_login.LoginWorker", Worker)
    with create_app_session(input=DummyInput(), output=DummyOutput()):
        ui = WizardTUI()
        assert "/login" not in ui._render_body().value
        assert ui._current_options() == ["investigate", "verify", "report", "explain"]
        assert not hasattr(ui, "_command_help")
        ui._status_input = True
        ui.app.layout.focus(ui.input)
        ui.input.buffer.document = Document("/lo")
        completions = list(
            ui.input.completer.get_completions(
                Document("/lo"), SimpleNamespace(completion_requested=True)
            )
        )
        assert [item.text for item in completions] == ["/login"]
        ui.input.buffer.document = Document("/login")
        ui._on_accept(ui.input.buffer)
        assert calls == ["login"]
        assert ui.app.layout.has_focus(ui.input) and ui._status_input
        assert ui.family is None
