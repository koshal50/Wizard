"""Account selection uses secure credentials; ownership is verified by the runtime."""

import httpx

from wizard.cli.runtime_client import account, usage
from wizard.cli.runtime_client.account import account_headers as secure_account_headers


def test_transport_uses_current_secure_credential_after_account_switch(monkeypatch):
    saved = {"access_token": "first-token"}

    class Store:
        def load(self):
            return saved.copy()

    monkeypatch.setattr(
        account, "account_origin", lambda: "https://accounts.example.test"
    )
    monkeypatch.setattr(account, "CredentialStore", lambda origin: Store())
    assert secure_account_headers() == {"Authorization": "Bearer first-token"}
    saved["access_token"] = "second-token"
    assert secure_account_headers() == {"Authorization": "Bearer second-token"}
    saved.clear()
    assert secure_account_headers() == {}


def test_status_after_switch_falls_back_to_current_accounts_totals(monkeypatch):
    requests = []
    monkeypatch.setattr(
        account, "account_headers", lambda: {"Authorization": "Bearer second-token"}
    )

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get(self, url, params, headers):
            assert headers == {"Authorization": "Bearer second-token"}
            requests.append(params)
            return httpx.Response(
                404 if params else 200,
                json={"totals": {"total_tokens": 7}},
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr(usage.httpx, "Client", Client)
    assert usage.status("first-accounts-run")["totals"]["total_tokens"] == 7
    assert requests == [{"run_id": "first-accounts-run"}, None]
