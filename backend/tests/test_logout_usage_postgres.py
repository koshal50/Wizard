"""Isolated accounts, actual logout/relogin, and permanent-account usage ownership."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_authorization_postgres import (
    approved,
    bind,
    context,
    exchange,
    initiate,
    post,
    register,
)
from wizard_kernel.api import account_auth, routes_investigations, routes_usage
from wizard_kernel.api.deps import get_manager
from wizard_kernel.contracts.status import LifecycleState
from wizard_kernel.session.manager import InvestigationManager
from wizard_kernel.storage import usage
from wizard_kernel.storage.usage_db import UsageDatabase, migrate

from wizard.cli.account_logout import ALREADY_OUT, LOGGED_OUT, logout


class Store:
    value = None

    def load(self):
        return self.value

    def delete(self):
        self.value = None


def reconnect(client):
    rid, verifier, ticket = initiate(client)
    assert bind(client, rid, ticket).status_code == 200
    pending = client.get("/api/cli/browser").json()
    assert pending["state"] == "pending" and "code" not in pending
    assert exchange(client, rid, verifier, "ABCDEF123456").status_code == 409
    code = post(client, "/api/cli/browser/approve").json()["code"]
    response = exchange(client, rid, verifier, code)
    assert response.status_code == 200
    return response.json(), code


def test_logout_relogin_switching_and_restart_preserve_each_accounts_usage(
    client, database, tmp_path, monkeypatch
):
    # The fixture owns a random schema; no application tables are migrated.
    migrate(database.pool.conninfo)
    db = UsageDatabase(database.pool.conninfo)
    monkeypatch.setenv("WIZARD_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WIZARD_ACCOUNT_URL", "https://accounts.example.test")
    store = usage.UsageStore()
    store.database = db
    manager = InvestigationManager()
    monkeypatch.setattr(usage, "get_usage", lambda: store)
    monkeypatch.setattr(routes_investigations.kernel_loop, "run", lambda *args: None)
    original_client = httpx.Client

    def verify(request):
        result = client.get(
            request.url.path,
            headers={"Authorization": request.headers["authorization"]},
        )
        return httpx.Response(result.status_code, json=result.json())

    monkeypatch.setattr(
        account_auth.httpx,
        "Client",
        lambda **kwargs: original_client(
            transport=httpx.MockTransport(verify), **kwargs
        ),
    )
    api = FastAPI()
    api.include_router(routes_investigations.router)
    api.include_router(routes_usage.router)
    api.dependency_overrides[get_manager] = lambda: manager
    api.dependency_overrides[routes_usage.local_usage] = lambda: store

    rid, verifier, first_code = approved(client)
    first = exchange(client, rid, verifier, first_code).json()
    first_id = context(client)["account"]["id"]
    credential = Store()
    credential.value = first

    with TestClient(api) as runtime:

        def headers(token):
            return {"Authorization": "Bearer " + token}

        def total(token):
            response = runtime.get("/v1/usage", headers=headers(token))
            assert response.status_code == 200, response.text
            assert response.json()["scope"] == "account"
            return response.json()["totals"]["total_tokens"]

        def consume(token, count):
            response = runtime.post(
                "/v1/investigations",
                headers=headers(token),
                json={
                    "repository_path": str(tmp_path),
                    "intent": "verify",
                    "targets": ["runtime"],
                    "session_id": "same-cli-session",
                    "account_id": "cannot-forge-this",
                },
            )
            assert response.status_code == 201, response.text
            inv = manager.get(response.json()["investigation_id"])
            with store.operation(inv):
                store.response(
                    SimpleNamespace(
                        json=lambda: {
                            "usage_events": [
                                {
                                    "event_id": uuid4().hex,
                                    "provider": "fixture",
                                    "model": "fixture",
                                    "input_tokens": count,
                                    "output_tokens": 0,
                                    "total_tokens": count,
                                    "usage_source": "provider-reported",
                                    "accuracy": "exact",
                                    "created_at": datetime.now(UTC).isoformat(),
                                }
                            ]
                        }
                    )
                )
                inv.state = LifecycleState.completed
            store.flush()
            return inv.id

        assert total(first["access_token"]) == 0
        first_run = consume(first["access_token"], 25)
        assert total(first["access_token"]) == 25
        assert logout("http://localhost", credential, client) == LOGGED_OUT
        assert logout("http://localhost", credential, client) == ALREADY_OUT
        assert context(client)["account"]["id"] == first_id  # Browser stays signed in.
        assert (
            runtime.get("/v1/usage", headers=headers(first["access_token"])).status_code
            == 401
        )
        assert (
            client.get(
                "/api/account/me", headers=headers(first["access_token"])
            ).status_code
            == 401
        )
        same, same_code = reconnect(client)
        assert same_code != first_code
        assert total(same["access_token"]) == 25
        consume(same["access_token"], 10)
        assert total(same["access_token"]) == 35

        # The explicit account switch preserves continuation but invalidates approval.
        rid, verifier, ticket = initiate(client)
        assert bind(client, rid, ticket).status_code == 200
        old_code = post(client, "/api/cli/browser/approve").json()["code"]
        assert post(client, "/api/cli/browser/change-account").status_code == 200
        assert context(client)["account"] is None
        assert context(client)["cli_pending"]
        assert register(client, "second@example.test").status_code == 303
        second_id = context(client)["account"]["id"]
        assert second_id != first_id
        new_code = post(client, "/api/cli/browser/approve").json()["code"]
        assert new_code != old_code
        assert exchange(client, rid, verifier, old_code).status_code == 400
        second = exchange(client, rid, verifier, new_code).json()
        assert total(second["access_token"]) == 0
        consume(second["access_token"], 7)
        assert total(second["access_token"]) == 7
        assert total(same["access_token"]) == 35
        assert (
            runtime.get(
                f"/v1/investigations/{first_run}/usage",
                headers=headers(second["access_token"]),
            ).status_code
            == 404
        )
        assert runtime.get(f"/v1/investigations/{first_run}/usage").status_code == 404

        # A new store/process reads database totals rather than an in-memory counter.
        restarted = usage.UsageStore()
        restarted.database = db
        api.dependency_overrides[routes_usage.local_usage] = lambda: restarted
        assert total(same["access_token"]) == 35
        assert total(second["access_token"]) == 7
        assert db.overall("account:" + first_id)["totals"]["total_tokens"] == 35
        assert db.overall("account:" + second_id)["totals"]["total_tokens"] == 7
    db.close()


def test_account_switch_requires_csrf_and_a_live_bound_request(client):
    approved(client)
    assert client.post("/api/cli/browser/change-account", json={}).status_code == 403
    assert post(client, "/api/cli/browser/change-account").status_code == 200
    assert context(client)["cli_pending"]
    assert context(client)["account"] is None
