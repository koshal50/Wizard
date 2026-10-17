"""Optional single-provider OIDC with state, nonce, PKCE and verified ID tokens."""

import base64
import hashlib
import os
import re
from datetime import timedelta
from urllib.parse import urlencode
from uuid import uuid4

import httpx
from fastapi import Request
from fastapi.responses import RedirectResponse

from backend.security import derived, digest, secret


def install_oidc(
    app, session, body, browser_mutation, rotate, auth_redirect, set_cookie, Denied
):
    def configuration():
        issuer = os.environ.get("WIZARD_OIDC_ISSUER", "").strip()
        client_id = os.environ.get("WIZARD_OIDC_CLIENT_ID")
        client_secret = os.environ.get("WIZARD_OIDC_CLIENT_SECRET")
        if not issuer or not client_id or not client_secret:
            raise Denied("oauth_unconfigured", 503)
        # Fail closed: no implicit insecure endpoints, even in local development.
        from urllib.parse import urlsplit

        parsed = urlsplit(issuer)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.query
            or parsed.fragment
            or parsed.username is not None
        ):
            raise Denied("oauth_configuration_invalid", 503)
        try:
            import jwt
        except ImportError:
            raise Denied("oauth_dependency_unavailable", 503) from None
        return issuer, client_id, client_secret, jwt

    async def metadata(client, issuer):
        response = await client.get(
            issuer.rstrip("/") + "/.well-known/openid-configuration"
        )
        response.raise_for_status()
        data = response.json()
        if data.get("issuer") != issuer:
            raise Denied("oauth_issuer_mismatch", 503)
        from urllib.parse import urlsplit

        for key in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
            url = urlsplit(data.get(key, ""))
            if url.scheme != "https" or not url.netloc or url.username or url.fragment:
                raise Denied("oauth_configuration_invalid", 503)
        return data

    @app.post("/oauth/oidc/start")
    async def start(request: Request):
        data = await body(request)
        row = browser_mutation(request, data)
        if row["account_id"]:
            return auth_redirect(row)
        issuer, client_id, _, _ = configuration()
        async with httpx.AsyncClient(
            timeout=8, follow_redirects=False, trust_env=False
        ) as client:
            meta = await metadata(client, issuer)
        state, nonce = secret(), secret()
        verifier = derived(app.state.settings.secret, "oidc-pkce", state)
        with app.state.db.connection() as conn:
            conn.execute(
                """INSERT INTO website_oidc_attempts(state_hash,session_id,nonce_hash,expires_at)
                VALUES (%s,%s,%s,%s)""",
                (
                    digest(state),
                    row["id"],
                    digest(nonce),
                    app.state.auth.clock() + timedelta(minutes=10),
                ),
            )
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        params = {
            "client_id": client_id,
            "response_type": "code",
            "scope": "openid email profile",
            "redirect_uri": app.state.settings.public_origin + "/oauth/oidc/callback",
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        return RedirectResponse(
            meta["authorization_endpoint"] + "?" + urlencode(params), 303
        )

    @app.get("/oauth/oidc/callback")
    async def callback(request: Request):
        row, _ = session(request)
        state = request.query_params.get("state", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}", state):
            raise Denied("oauth_state_invalid", 403)
        with app.state.db.connection() as conn:
            attempt = conn.execute(
                """DELETE FROM website_oidc_attempts WHERE state_hash=%s AND session_id=%s
                AND expires_at>%s RETURNING *""",
                (digest(state), row["id"], app.state.auth.clock()),
            ).fetchone()
        if not attempt:
            raise Denied("oauth_state_invalid", 403)
        if request.query_params.get("error") or row["account_id"]:
            raise Denied("oauth_cancelled_or_session_changed", 409)
        code = request.query_params.get("code", "")
        if not code or len(code) > 4096:
            raise Denied("oauth_code_invalid")
        issuer, client_id, client_secret, jwt = configuration()
        try:
            async with httpx.AsyncClient(
                timeout=8, follow_redirects=False, trust_env=False
            ) as client:
                meta = await metadata(client, issuer)
                tokens = await client.post(
                    meta["token_endpoint"],
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "code_verifier": derived(
                            app.state.settings.secret, "oidc-pkce", state
                        ),
                        "redirect_uri": app.state.settings.public_origin
                        + "/oauth/oidc/callback",
                    },
                )
                tokens.raise_for_status()
                id_token = tokens.json()["id_token"]
                keys = await client.get(meta["jwks_uri"])
                keys.raise_for_status()
            header = jwt.get_unverified_header(id_token)
            if header.get("alg") != "RS256":
                raise ValueError()
            jwks = keys.json().get("keys", [])
            key = next(
                k
                for k in jwks
                if k.get("kid") == header.get("kid") and k.get("kty") == "RSA"
            )
            claims = jwt.decode(
                id_token,
                jwt.PyJWK(key).key,
                algorithms=["RS256"],
                audience=client_id,
                issuer=issuer,
                options={"require": ["exp", "iat", "iss", "aud", "sub", "nonce"]},
            )
            if digest(claims["nonce"]) != attempt["nonce_hash"] or not claims.get(
                "sub"
            ):
                raise ValueError()
            if claims.get("azp", client_id) != client_id:
                raise ValueError()
            if (
                isinstance(claims["aud"], list)
                and len(claims["aud"]) > 1
                and claims.get("azp") != client_id
            ):
                raise ValueError()
            email = claims.get("email", "").strip().lower()
            if (
                claims.get("email_verified") is not True
                or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)
                or len(email) > 320
            ):
                raise ValueError()
        except Denied:
            raise
        except Exception:  # noqa: BLE001 -- provider responses and verification exceptions can contain tokens
            raise Denied("oauth_verification_failed", 401) from None
        with app.state.db.connection() as conn:
            # Prevent two callbacks on one browser session from changing its identity.
            current = conn.execute(
                "SELECT * FROM website_sessions WHERE id=%s FOR UPDATE", (row["id"],)
            ).fetchone()
            if current["account_id"] or current["token_hash"] != row["token_hash"]:
                raise Denied("oauth_session_changed", 409)
            identity = conn.execute(
                "SELECT account_id FROM website_oidc_identities WHERE issuer=%s AND subject=%s",
                (issuer, claims["sub"]),
            ).fetchone()
            if identity:
                aid = identity["account_id"]
            else:
                aid = uuid4()
                inserted = conn.execute(
                    """INSERT INTO website_accounts(id,email,full_name) VALUES (%s,%s,%s)
                    ON CONFLICT(email) DO NOTHING RETURNING id""",
                    (aid, email, str(claims.get("name") or email)[:200]),
                ).fetchone()
                if not inserted:
                    # Never link a password account by email alone.
                    raise Denied("oauth_account_link_required", 409)
                conn.execute(
                    "INSERT INTO website_oidc_identities(issuer,subject,account_id) VALUES (%s,%s,%s)",
                    (issuer, claims["sub"], aid),
                )
            token, seconds = rotate(conn, row, aid)
        response = auth_redirect(row)
        set_cookie(response, token, seconds)
        return response
