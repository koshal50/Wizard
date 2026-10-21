"""Website session and account API. Deploy behind the website's same-origin proxy."""

import hmac
import json
import re
from contextlib import asynccontextmanager
from datetime import timedelta
from urllib.parse import parse_qs
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse

from backend.authorization import Authorizations
from backend.config import Settings
from backend.db import Database
from backend.security import derived, digest, password_hash, password_matches, secret


class Denied(Exception):
    def __init__(self, code, status=400):
        self.code, self.status = code, status


def create_app(settings=None, database=None, clock=None):
    # Construction is lazy so importing the module does not open a database.
    @asynccontextmanager
    async def lifespan(app):
        if app.state.db is None:
            app.state.settings = Settings.environment()
            app.state.db = Database(app.state.settings.database_url)
        app.state.auth = Authorizations(app.state.db, app.state.settings.secret, clock)
        yield
        if database is None:
            app.state.db.close()

    app = FastAPI(
        title="Wizard Website Accounts",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.settings = settings
    app.state.db = database
    if database is not None:
        app.state.auth = Authorizations(database, settings.secret, clock)

    @app.exception_handler(Denied)
    async def denied(request, exc):
        headers = {"Retry-After": "60"} if exc.status == 429 else {}
        return JSONResponse(
            {"error": exc.code}, status_code=exc.status, headers=headers
        )

    @app.middleware("http")
    async def security(request, call_next):
        try:
            if request.url.path != "/health":
                cfg = app.state.settings
                if not cfg.local and request.url.scheme != "https":
                    raise Denied("https_required", 400)
                host = request.client.host if request.client else "unknown"
                path = (
                    "initiate" if request.url.path == "/api/cli/requests" else "general"
                )
                maximum = 10 if path == "initiate" else 120
                if not app.state.auth.limit("ip:" + host + ":" + path, maximum):
                    raise Denied("rate_limited", 429)
            response = await call_next(request)
        except Denied as exc:
            response = JSONResponse(
                {"error": exc.code},
                status_code=exc.status,
                headers={"Retry-After": "60"} if exc.status == 429 else {},
            )
        except Exception:  # noqa: BLE001 -- redact driver and request details at the HTTP boundary
            # Never return driver errors, submitted secrets, or connection URLs.
            response = JSONResponse({"error": "service_unavailable"}, status_code=503)
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "Pragma": "no-cache",
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
            }
        )
        return response

    def result(data):
        if "error" in data:
            raise Denied(data["error"], data["status"])
        return data

    def cookie_name():
        return "wizard_site" if app.state.settings.local else "__Host-wizard_site"

    def set_cookie(response, value, seconds):
        response.set_cookie(
            cookie_name(),
            value,
            max_age=seconds,
            httponly=True,
            secure=not app.state.settings.local,
            samesite="lax",
            path="/",
        )

    def session(request):
        token = request.cookies.get(cookie_name(), "")
        if not token or len(token) > 100:
            raise Denied("session_required", 401)
        with app.state.db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM website_sessions WHERE token_hash=%s AND expires_at>%s",
                (digest(token), app.state.auth.clock()),
            ).fetchone()
        if not row:
            raise Denied("session_required", 401)
        return row, token

    async def body(request):
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > 16384:
                raise Denied("body_too_large", 413)
        try:
            if (
                request.headers.get("content-type", "").split(";")[0]
                == "application/json"
            ):
                obj = json.loads(data)
                if not isinstance(obj, dict):
                    raise ValueError()
                if any(
                    not isinstance(v, str)
                    and not (k in {"acceptTerms", "remember"} and isinstance(v, bool))
                    for k, v in obj.items()
                ):
                    raise ValueError()
                return obj
            return {
                k: v[-1] for k, v in parse_qs(data.decode(), max_num_fields=20).items()
            }
        except (ValueError, UnicodeError):
            raise Denied("invalid_body") from None

    def browser_mutation(request, data):
        if request.headers.get("origin") != app.state.settings.public_origin:
            raise Denied("origin_rejected", 403)
        row, token = session(request)
        csrf = request.headers.get("x-csrf-token") or data.get("csrf", "")
        if not hmac.compare_digest(
            derived(app.state.settings.secret, "csrf", token), str(csrf)
        ):
            raise Denied("csrf_rejected", 403)
        return row

    def identifier(value):
        try:
            return str(UUID(str(value)))
        except (ValueError, TypeError):
            raise Denied("invalid_request_id") from None

    def proof(data):
        value = data.get("verifier", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{43,128}", value):
            raise Denied("invalid_proof", 403)
        return identifier(data.get("request_id")), value

    def rotate(conn, row, account_id, remember=False):
        value = secret()
        seconds = 30 * 86400 if remember else 7 * 86400
        updated = conn.execute(
            "UPDATE website_sessions SET token_hash=%s, account_id=%s, expires_at=%s "
            "WHERE id=%s AND token_hash=%s RETURNING id",
            (
                digest(value),
                account_id,
                app.state.auth.clock() + timedelta(seconds=seconds),
                row["id"],
                row["token_hash"],
            ),
        ).fetchone()
        if not updated:
            raise Denied("session_changed", 409)
        return value, seconds

    def auth_redirect(row):
        # Ignore all submitted returnTo values. Continuation lives only in this server session.
        return RedirectResponse(
            "/cli/connect" if row.get("pending_authorization") else "/", status_code=303
        )

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/api/auth/context")
    def context(request: Request):
        response = JSONResponse({})
        try:
            row, token = session(request)
        except Denied:
            token, sid = secret(), uuid4()
            with app.state.db.connection() as conn:
                row = conn.execute(
                    """INSERT INTO website_sessions(id,token_hash,expires_at)
                    VALUES (%s,%s,%s) RETURNING *""",
                    (sid, digest(token), app.state.auth.clock() + timedelta(hours=12)),
                ).fetchone()
            set_cookie(response, token, 12 * 3600)
        account = None
        if row["account_id"]:
            with app.state.db.connection() as conn:
                account = conn.execute(
                    "SELECT id,email,full_name FROM website_accounts WHERE id=%s",
                    (row["account_id"],),
                ).fetchone()
            account = {**account, "id": str(account["id"])} if account else None
        response.body = json.dumps(
            {
                "csrf": derived(app.state.settings.secret, "csrf", token),
                "account": account,
                "cli_pending": bool(row.get("pending_authorization")),
            }
        ).encode()
        response.headers["content-length"] = str(len(response.body))
        return response

    @app.post("/register")
    async def register(request: Request):
        data = await body(request)
        row = browser_mutation(request, data)
        email = data.get("email", "").strip().lower()
        name = data.get("fullName", "").strip()
        password = data.get("password", "")
        if (
            not re.fullmatch(r"[^\s@]{1,128}@[^\s@]{1,128}\.[^\s@]{1,64}", email)
            or not 1 <= len(name) <= 200
            or not 12 <= len(password) <= 256
            or password != data.get("confirmPassword")
            or data.get("acceptTerms") not in ("on", "true", True)
        ):
            raise Denied("invalid_registration")
        if not app.state.auth.limit("register:" + email, 5, 3600):
            raise Denied("rate_limited", 429)
        if row["account_id"]:
            raise Denied("already_authenticated", 409)
        encoded = password_hash(password)
        with app.state.db.connection() as conn:
            account = conn.execute(
                """INSERT INTO website_accounts(id,email,full_name,password_hash)
                VALUES (%s,%s,%s,%s) ON CONFLICT(email) DO NOTHING RETURNING id""",
                (uuid4(), email, name, encoded),
            ).fetchone()
            if not account:
                raise Denied("registration_unavailable", 409)
            token, seconds = rotate(conn, row, account["id"])
        response = auth_redirect(row)
        set_cookie(response, token, seconds)
        return response

    @app.post("/login")
    async def login(request: Request):
        data = await body(request)
        row = browser_mutation(request, data)
        email, password = (
            data.get("email", "").strip().lower(),
            data.get("password", ""),
        )
        if len(email) > 320 or len(password) > 256:
            raise Denied("invalid_credentials", 401)
        if not app.state.auth.limit("login:" + email, 10, 900):
            raise Denied("rate_limited", 429)
        if row["account_id"]:
            raise Denied("already_authenticated", 409)
        with app.state.db.connection() as conn:
            account = conn.execute(
                "SELECT * FROM website_accounts WHERE email=%s", (email,)
            ).fetchone()
            encoded = (
                account["password_hash"]
                if account and account["password_hash"]
                else app.state.dummy_password
            )
            valid = password_matches(password, encoded)
            if not valid or not account or not account["password_hash"]:
                raise Denied("invalid_credentials", 401)
            token, seconds = rotate(
                conn, row, account["id"], bool(data.get("remember"))
            )
        response = auth_redirect(row)
        set_cookie(response, token, seconds)
        return response

    @app.post("/forgot-password")
    async def forgot(request: Request):
        data = await body(request)
        browser_mutation(request, data)
        # No mail delivery/reset provider exists in this repository.
        raise Denied("password_reset_delivery_unconfigured", 503)

    @app.post("/logout")
    async def logout(request: Request):
        data = await body(request)
        row = browser_mutation(request, data)
        with app.state.db.connection() as conn:
            # Lock in the same order as authorization operations to avoid lost mutations.
            conn.execute(
                "UPDATE cli_authorizations SET state='cancelled' WHERE browser_session_id=%s "
                "AND state IN ('pending','approved')",
                (row["id"],),
            )
            token, seconds = rotate(conn, row, None)
            conn.execute(
                "UPDATE website_sessions SET pending_authorization=NULL WHERE id=%s",
                (row["id"],),
            )
        response = JSONResponse({"signed_out": True})
        set_cookie(response, token, seconds)
        return response

    @app.post("/api/cli/requests", status_code=201)
    async def initiate(request: Request):
        # No ambient cookie authentication; cross-origin browser requests are forbidden.
        if request.headers.get("origin"):
            raise Denied("cli_only", 403)
        data = await body(request)
        challenge = data.get("verifier_hash", "")
        if not re.fullmatch("[a-f0-9]{64}", challenge):
            raise Denied("invalid_challenge")
        data = app.state.auth.initiate(challenge)
        data["authorization_url"] = (
            app.state.settings.public_origin
            + "/cli/authorize#request_id="
            + data["request_id"]
            + "&ticket="
            + data.pop("browser_ticket")
        )
        return data

    @app.post("/api/cli/browser/bind")
    async def bind(request: Request):
        data = await body(request)
        row = browser_mutation(request, data)
        ticket = data.get("ticket", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}", ticket):
            raise Denied("invalid_context")
        return result(
            app.state.auth.bind(identifier(data.get("request_id")), ticket, row)
        )

    @app.get("/api/cli/browser")
    def browser_status(request: Request):
        row, _ = session(request)
        return result(app.state.auth.browser(row))

    @app.post("/api/cli/browser/approve")
    async def approve(request: Request):
        data = await body(request)
        row = browser_mutation(request, data)
        if not app.state.auth.limit("issue:" + str(row["id"]), 10):
            raise Denied("rate_limited", 429)
        return result(app.state.auth.browser(row, approve=True))

    @app.post("/api/cli/browser/cancel")
    async def browser_cancel(request: Request):
        data = await body(request)
        row = browser_mutation(request, data)
        return result(app.state.auth.browser(row, cancel=True))

    @app.post("/api/cli/browser/change-account")
    async def change_account(request: Request):
        data = await body(request)
        row = browser_mutation(request, data)
        with app.state.db.connection() as conn:
            pending = conn.execute(
                "SELECT * FROM cli_authorizations WHERE id=%s AND browser_session_id=%s FOR UPDATE",
                (row.get("pending_authorization"), row["id"]),
            ).fetchone()
            if not pending:
                raise Denied("missing_context", 404)
            if (
                pending["state"] not in {"pending", "approved"}
                or pending["expires_at"] <= app.state.auth.clock()
            ):
                raise Denied("expired_or_cancelled", 410)
            # Preserve the request, invalidate its previous approval/code, and
            # rotate the browser session before allowing a different account.
            token, seconds = rotate(conn, row, None)
            conn.execute(
                "UPDATE cli_authorizations SET state='pending', account_id=NULL, "
                "code_nonce=NULL, code_hash=NULL, code_expires_at=NULL WHERE id=%s",
                (pending["id"],),
            )
        response = JSONResponse(
            {"continue_to": "/login.html?returnTo=%2Fcli%2Fconnect"}
        )
        set_cookie(response, token, seconds)
        return response

    async def cli_action(request, action):
        if request.headers.get("origin"):
            raise Denied("cli_only", 403)
        data = await body(request)
        rid, verifier = proof(data)
        if not app.state.auth.limit("proof:" + rid, 30):
            raise Denied("rate_limited", 429)
        return result(
            app.state.auth.exchange(
                rid,
                verifier,
                data.get("code"),
                recover=action == "recover",
                cancel=action == "cancel",
            )
        )

    @app.post("/api/cli/exchange")
    async def exchange(request: Request):
        return await cli_action(request, "exchange")

    @app.post("/api/cli/recover")
    async def recover(request: Request):
        return await cli_action(request, "recover")

    @app.post("/api/cli/cancel")
    async def cli_cancel(request: Request):
        return await cli_action(request, "cancel")

    def bearer(request):
        value = request.headers.get("authorization", "")
        if not re.fullmatch(r"Bearer wa_[a-f0-9-]{36}\.[a-f0-9]{64}", value):
            raise Denied("credential_required", 401)
        with app.state.db.connection() as conn:
            row = conn.execute(
                """SELECT c.id AS credential_id,c.authorization_id,c.expires_at,a.id,a.email,a.full_name
                FROM account_cli_credentials c JOIN website_accounts a ON a.id=c.account_id
                WHERE c.token_hash=%s AND c.revoked_at IS NULL AND c.expires_at>%s""",
                (digest(value[7:]), app.state.auth.clock()),
            ).fetchone()
        if not row:
            raise Denied("credential_expired_or_revoked", 401)
        return row

    @app.get("/api/account/me")
    def me(request: Request):
        row = bearer(request)
        return {
            "account": {
                "id": str(row["id"]),
                "email": row["email"],
                "full_name": row["full_name"],
            },
            "credential_expires_at": row["expires_at"].isoformat(),
        }

    def investigation_owner(request):
        if request.headers.get("authorization"):
            return bearer(request)["id"]
        row, _ = session(request)
        if not row["account_id"]:
            raise Denied("session_required", 401)
        return row["account_id"]

    @app.post("/api/investigations", status_code=201)
    async def save_architecture(request: Request):
        from backend.architecture import ArchitectureGraph
        from pydantic import ValidationError
        from psycopg.types.json import Jsonb

        # CLI-only writes reuse the existing credential; browser reads use sessions.
        owner = bearer(request)["id"]
        raw = bytearray()
        async for chunk in request.stream():
            if len(raw) + len(chunk) > 2_000_000:
                raise Denied("body_too_large", 413)
            raw.extend(chunk)
        try:
            graph = ArchitectureGraph.model_validate_json(raw)
        except (ValidationError, ValueError, RecursionError):
            raise Denied("invalid_architecture_graph", 422) from None
        public_id = uuid4()
        with app.state.db.connection() as conn:
            conn.execute(
                "INSERT INTO architecture_investigations "
                "(id,owner_id,title,repository_name,status,schema_version,graph) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (public_id, owner, graph.title, graph.repository_name, graph.status,
                 graph.schema_version, Jsonb(graph.model_dump())),
            )
        # Leaving the connection context commits before success is returned.
        return {"investigation_id": str(public_id)}

    @app.get("/api/investigations")
    def saved_architectures(request: Request):
        owner = investigation_owner(request)
        with app.state.db.connection() as conn:
            rows = conn.execute(
                "SELECT id,title,repository_name,status,created_at FROM architecture_investigations "
                "WHERE owner_id=%s ORDER BY created_at DESC LIMIT 50", (owner,),
            ).fetchall()
        return {"investigations": [{**r, "id": str(r["id"]), "created_at": r["created_at"].isoformat()} for r in rows]}

    @app.get("/api/investigations/{investigation_id}")
    def saved_architecture(investigation_id: str, request: Request):
        owner = investigation_owner(request)
        public_id = identifier(investigation_id)
        with app.state.db.connection() as conn:
            row = conn.execute(
                "SELECT id,graph,created_at FROM architecture_investigations WHERE id=%s AND owner_id=%s",
                (public_id, owner),
            ).fetchone()
        if not row:
            raise Denied("investigation_not_found", 404)
        return {"investigation_id": str(row["id"]), "graph": row["graph"],
                "created_at": row["created_at"].isoformat()}

    @app.delete("/api/account/credential")
    def revoke(request: Request):
        row = bearer(request)
        with app.state.db.connection() as conn:
            conn.execute(
                "SELECT id FROM cli_authorizations WHERE id=%s FOR UPDATE",
                (row["authorization_id"],),
            )
            conn.execute(
                "UPDATE account_cli_credentials SET revoked_at=%s WHERE id=%s",
                (app.state.auth.clock(), row["credential_id"]),
            )
            conn.execute(
                "UPDATE cli_authorizations SET state='cancelled' WHERE id=%s",
                (row["authorization_id"],),
            )
        return {"revoked": True}

    app.state.dummy_password = password_hash(secret())
    # OIDC provider integration is optional; no provider is inferred from the frontend.
    from backend.oidc import install_oidc

    install_oidc(
        app, session, body, browser_mutation, rotate, auth_redirect, set_cookie, Denied
    )
    return app


app = create_app()
