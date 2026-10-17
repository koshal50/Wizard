"""OIDC integration with signed ID tokens and a simulated provider, not real-provider E2E."""

import base64
import hashlib
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from test_authorization_postgres import bind, context, initiate, post, register


@pytest.fixture
def provider(monkeypatch):
    jwt = pytest.importorskip("jwt")
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    jwk["kid"] = "test-key"
    for name, value in {
        "WIZARD_OIDC_ISSUER": "https://identity.example.test",
        "WIZARD_OIDC_CLIENT_ID": "wizard-test",
        "WIZARD_OIDC_CLIENT_SECRET": "test-only-secret",
    }.items():
        monkeypatch.setenv(name, value)
    state = {
        "nonce": "",
        "aud": "wizard-test",
        "email": "oidc@example.test",
        "verified": True,
    }
    captured = []

    def handle(request):
        captured.append(request)
        if request.url.path == "/.well-known/openid-configuration":
            return httpx.Response(
                200,
                json={
                    "issuer": "https://identity.example.test",
                    "authorization_endpoint": "https://identity.example.test/authorize",
                    "token_endpoint": "https://identity.example.test/token",
                    "jwks_uri": "https://identity.example.test/keys",
                },
            )
        if request.url.path == "/keys":
            return httpx.Response(200, json={"keys": [jwk]})
        if request.url.path == "/token":
            now = int(datetime.now(UTC).timestamp())
            token = jwt.encode(
                {
                    "iss": "https://identity.example.test",
                    "aud": state["aud"],
                    "sub": "provider-subject",
                    "iat": now,
                    "exp": now + 300,
                    "nonce": state["nonce"],
                    "email": state["email"],
                    "email_verified": state["verified"],
                },
                key,
                algorithm="RS256",
                headers={"kid": "test-key"},
            )
            return httpx.Response(200, json={"id_token": token})
        raise AssertionError(request.url)

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handle), **kwargs),
    )
    return state, captured


def start(client):
    response = post(client, "/oauth/oidc/start")
    assert response.status_code == 303, response.text
    return parse_qs(urlsplit(response.headers["location"]).query)


def test_oidc_preserves_pending_context_state_nonce_pkce_and_verified_account(
    client, provider
):
    state, captured = provider
    rid, _, ticket = initiate(client)
    assert bind(client, rid, ticket).status_code == 200
    params = start(client)
    assert params["code_challenge_method"] == ["S256"]
    state["nonce"] = params["nonce"][0]
    callback = "/oauth/oidc/callback?state=" + params["state"][0] + "&code=test-code"
    response = client.get(callback, follow_redirects=False)
    assert response.status_code == 303, response.text
    assert response.headers["location"] == "/cli/connect"
    assert context(client)["account"]["email"] == "oidc@example.test"
    assert post(client, "/api/cli/browser/approve").status_code == 200
    token_request = next(r for r in captured if r.url.path == "/token")
    verifier = parse_qs(token_request.content.decode())["code_verifier"][0]
    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    assert expected == params["code_challenge"][0]
    assert client.get(callback).status_code == 403  # consumed state


@pytest.mark.parametrize("invalid", ["nonce", "aud", "verified"])
def test_oidc_rejects_tampered_claims_without_authenticating(client, provider, invalid):
    state, _ = provider
    params = start(client)
    state["nonce"] = params["nonce"][0]
    state[invalid] = False if invalid == "verified" else "tampered"
    response = client.get(
        "/oauth/oidc/callback?state=" + params["state"][0] + "&code=test"
    )
    assert response.status_code == 401
    assert context(client)["account"] is None


def test_oauth_does_not_auto_link_existing_account_by_email(client, provider):
    state, _ = provider
    assert register(client, "oidc@example.test").status_code == 303
    assert post(client, "/logout").status_code == 200
    params = start(client)
    state["nonce"] = params["nonce"][0]
    response = client.get(
        "/oauth/oidc/callback?state=" + params["state"][0] + "&code=test"
    )
    assert response.status_code == 409
    assert response.json()["error"] == "oauth_account_link_required"
    assert context(client)["account"] is None
