import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import pytest

from backend.authorization import Authorizations
from backend.security import digest

ORIGIN = {"Origin": "http://localhost"}


def context(client):
    response = client.get("/api/auth/context")
    assert response.status_code == 200, response.text
    return response.json()


def post(client, path, data=None):
    ctx = context(client)
    return client.post(
        path,
        json=data or {},
        headers={**ORIGIN, "X-CSRF-Token": ctx["csrf"]},
        follow_redirects=False,
    )


def initiate(client, verifier=None):
    verifier = verifier or secrets.token_urlsafe(32)
    response = client.post(
        "/api/cli/requests", json={"verifier_hash": digest(verifier)}
    )
    assert response.status_code == 201, response.text
    data = response.json()
    fragment = parse_qs(urlsplit(data["authorization_url"]).fragment)
    return data["request_id"], verifier, fragment["ticket"][0]


def bind(client, rid, ticket):
    return post(client, "/api/cli/browser/bind", {"request_id": rid, "ticket": ticket})


def register(client, email="account@example.test"):
    return post(
        client,
        "/register",
        {
            "email": email,
            "fullName": "Test Account",
            "password": "a-secure-password-123",
            "confirmPassword": "a-secure-password-123",
            "acceptTerms": "on",
        },
    )


def approved(client):
    rid, verifier, ticket = initiate(client)
    assert bind(client, rid, ticket).status_code == 200
    assert register(client).status_code == 303
    response = post(client, "/api/cli/browser/approve")
    assert response.status_code == 200, response.text
    return rid, verifier, response.json()["code"]


def exchange(client, rid, verifier, code, path="/api/cli/exchange"):
    return client.post(
        path, json={"request_id": rid, "verifier": verifier, "code": code}
    )


def test_full_registration_exchange_verification_recovery_replay_and_revocation(
    client, database
):
    rid, verifier, code = approved(client)
    again = post(client, "/api/cli/browser/approve")
    assert again.json()["code"] == code
    assert again.json()["request_id"] == rid
    assert len(code) == 12
    issued = exchange(client, rid, verifier, code)
    assert issued.status_code == 200, issued.text
    token = issued.json()["access_token"]
    me = client.get("/api/account/me", headers={"Authorization": "Bearer " + token})
    assert me.json()["account"]["email"] == "account@example.test"
    assert client.get("/api/cli/browser").json()["state"] == "exchanged"
    assert exchange(client, rid, verifier, code).status_code == 409
    recovered = exchange(client, rid, verifier, "", "/api/cli/recover")
    assert recovered.json() == issued.json()
    with database.connection() as conn:
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM account_cli_credentials"
            ).fetchone()["n"]
            == 1
        )
        auth = conn.execute("SELECT * FROM cli_authorizations").fetchone()
        assert auth["code_hash"] == digest(code) and auth["code_hash"] != code
        assert conn.execute(
            "SELECT token_hash FROM account_cli_credentials"
        ).fetchone()["token_hash"] == digest(token)
    assert (
        client.delete(
            "/api/account/credential", headers={"Authorization": "Bearer " + token}
        ).status_code
        == 200
    )
    assert (
        client.get(
            "/api/account/me", headers={"Authorization": "Bearer " + token}
        ).status_code
        == 401
    )
    assert exchange(client, rid, verifier, "", "/api/cli/recover").status_code == 410


def test_unauthenticated_direct_tampered_context_csrf_and_origin(client):
    assert client.get("/api/cli/browser").status_code == 401
    assert client.get("/cli/complete").status_code == 404
    assert post(client, "/api/cli/browser/approve").status_code == 404
    rid, verifier, ticket = initiate(client)
    assert bind(client, rid, secrets.token_urlsafe(32)).status_code == 404
    assert (
        bind(client, rid, ticket)
        .json()["continue_to"]
        .startswith("/login.html?returnTo=")
    )
    assert post(client, "/api/cli/browser/approve").status_code == 401
    assert client.get("/api/cli/browser").status_code == 401
    assert client.post("/login", json={"email": "x"}, headers=ORIGIN).status_code == 403
    csrf = context(client)["csrf"]
    assert (
        client.post(
            "/api/cli/browser/cancel",
            json={},
            headers={"Origin": "https://evil.test", "X-CSRF-Token": csrf},
        ).status_code
        == 403
    )
    assert exchange(client, rid, secrets.token_urlsafe(32), "0" * 12).status_code == 403
    assert exchange(client, rid, verifier, "0" * 12).status_code == 409
    assert (
        client.post(
            "/api/cli/requests",
            json={"verifier_hash": digest(verifier)},
            headers=ORIGIN,
        ).status_code
        == 403
    )


def test_login_continuation_is_server_side_and_normal_auth_has_no_cli_redirect(client):
    assert register(client).headers["location"] == "/"
    assert post(client, "/logout").status_code == 200
    rid, _verifier, ticket = initiate(client)
    assert bind(client, rid, ticket).status_code == 200
    response = post(
        client,
        "/login",
        {
            "email": "account@example.test",
            "password": "a-secure-password-123",
            "returnTo": "https://evil.test",
        },
    )
    assert (
        response.status_code == 303 and response.headers["location"] == "/cli/connect"
    )
    assert post(client, "/api/cli/browser/approve").status_code == 200
    # An already authenticated continuation does not ask for credentials again.
    rid2, _, ticket2 = initiate(client)
    assert rid2 != rid
    assert bind(client, rid2, ticket2).json()["continue_to"] == "/cli/connect"
    pending = client.get("/api/cli/browser").json()
    assert pending["state"] == "pending"
    assert pending["request_id"] == rid2


@pytest.mark.parametrize("seconds", [300, 600])
def test_expiry_boundaries(client, clock, seconds):
    rid, verifier, code = approved(client)
    clock.now += timedelta(seconds=seconds)
    assert exchange(client, rid, verifier, code).status_code == 410
    assert client.get("/api/cli/browser").status_code == 410


def test_invalid_code_attempts_are_committed_and_limited(client):
    rid, verifier, code = approved(client)
    for _ in range(5):
        assert exchange(client, rid, verifier, "not-the-code").status_code == 400
    assert exchange(client, rid, verifier, code).status_code == 429


def test_recovery_expiry_and_cancel_revokes_response_lost_issuance(client, clock):
    rid, verifier, code = approved(client)
    issued = exchange(client, rid, verifier, code).json()
    clock.now += timedelta(seconds=120)
    assert exchange(client, rid, verifier, "", "/api/cli/recover").status_code == 410
    assert exchange(client, rid, verifier, "", "/api/cli/cancel").status_code == 200
    assert (
        client.get(
            "/api/account/me",
            headers={"Authorization": "Bearer " + issued["access_token"]},
        ).status_code
        == 401
    )


def test_browser_cancellation_and_expired_pending(client, clock):
    rid, verifier, ticket = initiate(client)
    assert bind(client, rid, ticket).status_code == 200
    assert post(client, "/api/cli/browser/cancel").json()["state"] == "cancelled"
    assert exchange(client, rid, verifier, "0" * 12).status_code == 410
    rid, verifier, ticket = initiate(client)
    clock.now += timedelta(seconds=600)
    assert bind(client, rid, ticket).status_code == 410


def test_concurrent_exchange_is_atomic(client, database, clock):
    rid, verifier, code = approved(client)
    service = Authorizations(database, b"x" * 32, clock)
    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(
            pool.map(lambda _: service.exchange(rid, verifier, code), range(8))
        )
    assert sum("access_token" in x for x in outcomes) == 1
    assert sum(x.get("error") == "already_exchanged" for x in outcomes) == 7
    with database.connection() as conn:
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM account_cli_credentials"
            ).fetchone()["n"]
            == 1
        )


def test_cancel_exchange_race_cannot_leave_a_live_credential(client, database, clock):
    rid, verifier, code = approved(client)
    service = Authorizations(database, b"x" * 32, clock)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(service.exchange, rid, verifier, code),
            pool.submit(service.exchange, rid, verifier, cancel=True),
        ]
        outcomes = [future.result() for future in futures]
    with database.connection() as conn:
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM account_cli_credentials WHERE revoked_at IS NULL"
            ).fetchone()["n"]
            == 0
        )
    assert outcomes[1]["state"] == "cancelled"


def test_issuance_database_failure_rolls_back_consumption(client, database):
    rid, verifier, code = approved(client)
    with database.connection() as conn:
        conn.execute(
            "ALTER TABLE account_cli_credentials ADD CONSTRAINT test_reject CHECK (false)"
        )
    assert exchange(client, rid, verifier, code).status_code == 503
    with database.connection() as conn:
        assert (
            conn.execute("SELECT state FROM cli_authorizations").fetchone()["state"]
            == "approved"
        )
        conn.execute("ALTER TABLE account_cli_credentials DROP CONSTRAINT test_reject")
    assert exchange(client, rid, verifier, code).status_code == 200


def test_new_browser_cannot_bind_another_sessions_request(client, database, clock):
    from fastapi.testclient import TestClient

    rid, _verifier, ticket = initiate(client)
    assert bind(client, rid, ticket).status_code == 200
    with TestClient(client.app, base_url="http://localhost") as other:
        assert bind(other, rid, ticket).status_code == 409
        assert post(other, "/api/cli/browser/approve").status_code == 404


def test_no_account_reassignment_after_approval(client, database):
    rid, verifier, code = approved(client)
    import uuid

    with database.connection() as conn:
        aid = uuid.uuid4()
        conn.execute(
            "INSERT INTO website_accounts(id,email,full_name) VALUES (%s,'other@example.test','Other')",
            (aid,),
        )
        conn.execute("UPDATE website_sessions SET account_id=%s", (aid,))
    assert client.get("/api/cli/browser").status_code == 403
    issued = exchange(client, rid, verifier, code).json()
    assert (
        client.get(
            "/api/account/me",
            headers={"Authorization": "Bearer " + issued["access_token"]},
        ).json()["account"]["email"]
        == "account@example.test"
    )


def test_initiation_limit_malformed_body_and_unconfigured_services(client):
    for _ in range(10):
        initiate(client)
    assert (
        client.post("/api/cli/requests", json={"verifier_hash": "a" * 64}).status_code
        == 429
    )
    assert client.post("/login", content="[" * 20000).status_code == 413
    assert post(client, "/oauth/oidc/start").status_code == 503
    assert client.get("/oauth/oidc/callback?state=bad").status_code == 403
    assert (
        post(client, "/forgot-password", {"email": "account@example.test"}).status_code
        == 503
    )


def test_expiry_is_checked_after_waiting_for_transaction_lock(client, database, clock):
    import threading
    import time

    rid, verifier, code = approved(client)
    service = Authorizations(database, b"x" * 32, clock)
    outcomes = []
    with database.connection() as conn:
        conn.execute("SELECT id FROM cli_authorizations WHERE id=%s FOR UPDATE", (rid,))
        thread = threading.Thread(
            target=lambda: outcomes.append(service.exchange(rid, verifier, code))
        )
        thread.start()
        time.sleep(0.1)
        clock.now += timedelta(seconds=300)
    thread.join(3)
    assert not thread.is_alive()
    assert outcomes[0]["error"] == "code_expired"


def test_logout_preserves_already_issued_cli_credentials(client):
    rid, verifier, code = approved(client)
    token = exchange(client, rid, verifier, code).json()["access_token"]
    assert post(client, "/logout").status_code == 200
    assert (
        client.get(
            "/api/account/me", headers={"Authorization": "Bearer " + token}
        ).status_code
        == 200
    )


def test_repeated_approval_after_code_expiry_never_mints_replacement(client, clock):
    approved(client)
    clock.now += timedelta(seconds=300)
    assert post(client, "/api/cli/browser/approve").status_code == 410


def test_malformed_field_types_and_cache_headers(client):
    response = client.post("/api/cli/requests", json={"verifier_hash": True})
    assert response.status_code == 400
    assert response.headers["cache-control"] == "no-store"
    assert "access-control-allow-origin" not in response.headers
    assert (
        client.post(
            "/api/cli/exchange", json={"request_id": "bad", "verifier": []}
        ).status_code
        == 400
    )


def test_credential_expiry_and_cleanup_preserves_live_credentials(
    client, database, clock
):
    from backend.db import cleanup

    rid, verifier, code = approved(client)
    token = exchange(client, rid, verifier, code).json()["access_token"]
    with database.connection() as conn:
        conn.execute("UPDATE cli_authorizations SET expires_at=now()-interval '2 days'")
        conn.execute("UPDATE website_sessions SET expires_at=now()-interval '2 days'")
    cleanup(database.pool.conninfo)
    assert (
        client.get(
            "/api/account/me", headers={"Authorization": "Bearer " + token}
        ).status_code
        == 200
    )
    clock.now += timedelta(days=30)
    assert (
        client.get(
            "/api/account/me", headers={"Authorization": "Bearer " + token}
        ).status_code
        == 401
    )


def test_browser_cancel_exchange_race_has_a_single_linearized_result(
    client, database, clock
):
    rid, verifier, code = approved(client)
    service = Authorizations(database, b"x" * 32, clock)
    with database.connection() as conn:
        session = conn.execute("SELECT * FROM website_sessions").fetchone()
    with ThreadPoolExecutor(max_workers=2) as pool:
        redeem = pool.submit(service.exchange, rid, verifier, code)
        cancel = pool.submit(service.browser, session, cancel=True)
        issued, cancellation = redeem.result(), cancel.result()
    with database.connection() as conn:
        count = conn.execute(
            "SELECT count(*) AS n FROM account_cli_credentials"
        ).fetchone()["n"]
    if cancellation.get("state") == "cancelled":
        assert count == 0 and issued["error"] == "expired_or_cancelled"
    else:
        assert cancellation["error"] == "already_exchanged" and count == 1
        assert "access_token" in issued
