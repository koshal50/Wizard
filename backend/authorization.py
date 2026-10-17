"""Transactional account authorization. All denial results commit attempt counters."""

import hmac
import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from backend.security import derived, digest, secret

REQUEST_TTL = 600
CODE_TTL = 300
RECOVERY_TTL = 120
CREDENTIAL_TTL = 30 * 86400


def failure(code, status=400):
    return {"error": code, "status": status}


class Authorizations:
    def __init__(self, db, key, clock=None):
        self.db, self.key = db, key
        self.clock = clock or (lambda: datetime.now(UTC))

    def limit(self, bucket, maximum, seconds=60):
        now = self.clock()
        with self.db.connection() as conn:
            row = conn.execute(
                """INSERT INTO account_rate_limits(bucket, starts_at, hits)
                VALUES (%s,%s,1) ON CONFLICT(bucket) DO UPDATE SET
                starts_at=CASE WHEN account_rate_limits.starts_at <= %s THEN %s ELSE account_rate_limits.starts_at END,
                hits=CASE WHEN account_rate_limits.starts_at <= %s THEN 1 ELSE account_rate_limits.hits+1 END
                RETURNING hits""",
                (
                    digest(bucket),
                    now,
                    now - timedelta(seconds=seconds),
                    now,
                    now - timedelta(seconds=seconds),
                ),
            ).fetchone()
        return row["hits"] <= maximum

    def initiate(self, challenge):
        rid, ticket, now = str(uuid4()), secret(), self.clock()
        expires = now + timedelta(seconds=REQUEST_TTL)
        with self.db.connection() as conn:
            conn.execute(
                """INSERT INTO cli_authorizations(id, verifier_hash, ticket_hash, created_at, expires_at)
                VALUES (%s,%s,%s,%s,%s)""",
                (rid, challenge, digest(ticket), now, expires),
            )
        return {
            "request_id": rid,
            "browser_ticket": ticket,
            "expires_at": expires.isoformat(),
        }

    def bind(self, rid, ticket, session):
        now = self.clock()
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM cli_authorizations WHERE id=%s FOR UPDATE", (rid,)
            ).fetchone()
            now = (
                self.clock()
            )  # Check expiry after acquiring a potentially contended row lock.
            if not row or not hmac.compare_digest(row["ticket_hash"], digest(ticket)):
                return failure("invalid_context", 404)
            if row["expires_at"] <= now or row["state"] == "cancelled":
                return failure("expired_or_cancelled", 410)
            if row["browser_session_id"] and str(row["browser_session_id"]) != str(
                session["id"]
            ):
                return failure("context_already_bound", 409)
            conn.execute(
                "UPDATE cli_authorizations SET browser_session_id=%s WHERE id=%s",
                (session["id"], rid),
            )
            conn.execute(
                "UPDATE website_sessions SET pending_authorization=%s WHERE id=%s",
                (rid, session["id"]),
            )
        return {
            "request_id": rid,
            "continue_to": "/cli/connect"
            if session["account_id"]
            else "/login.html?returnTo=%2Fcli%2Fconnect",
        }

    def code(self, row):
        # Reproducible only with the service key; plaintext codes never persist.
        raw = derived(
            self.key, "authorization-code", str(row["id"]) + ":" + row["code_nonce"]
        )
        return raw[:12].upper()

    def browser(self, session, approve=False, cancel=False):
        rid = session.get("pending_authorization")
        if not rid:
            return failure("missing_context", 404)
        now = self.clock()
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT * FROM cli_authorizations WHERE id=%s FOR UPDATE", (rid,)
            ).fetchone()
            now = (
                self.clock()
            )  # Check expiry after acquiring a potentially contended row lock.
            if not row or str(row["browser_session_id"]) != str(session["id"]):
                return failure("invalid_context", 404)
            current = conn.execute(
                "SELECT * FROM website_sessions WHERE id=%s FOR UPDATE",
                (session["id"],),
            ).fetchone()
            now = self.clock()
            if (
                not current
                or current["expires_at"] <= now
                or current["token_hash"] != session["token_hash"]
                or current["account_id"] != session["account_id"]
            ):
                return failure("session_changed", 409)
            if cancel:
                if row["state"] == "exchanged":
                    return failure("already_exchanged", 409)
                conn.execute(
                    "UPDATE cli_authorizations SET state='cancelled' WHERE id=%s",
                    (rid,),
                )
                return {"state": "cancelled", "request_id": str(rid)}
            if not session["account_id"]:
                return failure("authentication_required", 401)
            if row["account_id"] and row["account_id"] != session["account_id"]:
                return failure("account_mismatch", 403)
            if row["state"] == "cancelled":
                return failure("cancelled", 410)
            if row["expires_at"] <= now:
                return failure("expired", 410)
            if row["state"] == "exchanged":
                return {
                    "state": "exchanged",
                    "request_id": str(rid),
                    "complete_to": "/cli/complete",
                }
            if row["attempts"] >= 5:
                return failure("attempt_limit", 429)
            if row["code_expires_at"] and row["code_expires_at"] <= now:
                return failure("code_expired", 410)
            if approve and row["state"] == "pending":
                row["code_nonce"] = secrets.token_hex(16)
                row["code_expires_at"] = min(
                    row["expires_at"], now + timedelta(seconds=CODE_TTL)
                )
                row["state"] = "approved"
                conn.execute(
                    """UPDATE cli_authorizations SET account_id=%s, state='approved', code_nonce=%s,
                    code_hash=%s, code_expires_at=%s WHERE id=%s""",
                    (
                        session["account_id"],
                        row["code_nonce"],
                        digest(self.code(row)),
                        row["code_expires_at"],
                        rid,
                    ),
                )
            result = {
                "state": row["state"],
                "request_id": str(rid),
                "expires_at": row["expires_at"].isoformat(),
            }
            if row["state"] == "approved":
                result.update(
                    code=self.code(row),
                    code_expires_at=row["code_expires_at"].isoformat(),
                )
            return result

    def proof_row(self, conn, rid, verifier):
        row = conn.execute(
            "SELECT * FROM cli_authorizations WHERE id=%s FOR UPDATE", (rid,)
        ).fetchone()
        if not row or not hmac.compare_digest(row["verifier_hash"], digest(verifier)):
            return None
        return row

    def token(self, rid, verifier):
        return (
            "wa_"
            + str(rid)
            + "."
            + derived(self.key, "cli-credential", str(rid) + ":" + verifier)
        )

    def issued(self, conn, row, verifier):
        token = self.token(row["id"], verifier)
        credential = conn.execute(
            """SELECT expires_at FROM account_cli_credentials
            WHERE authorization_id=%s AND token_hash=%s AND revoked_at IS NULL AND expires_at>%s""",
            (row["id"], digest(token), self.clock()),
        ).fetchone()
        if not credential:
            return failure("credential_unavailable", 410)
        return {
            "access_token": token,
            "token_type": "Bearer",
            "expires_at": credential["expires_at"].isoformat(),
        }

    def exchange(self, rid, verifier, code=None, recover=False, cancel=False):
        now = self.clock()
        with self.db.connection() as conn:
            row = self.proof_row(conn, rid, verifier)
            now = self.clock()
            if not row:
                return failure("invalid_proof", 403)
            if cancel:
                if row["state"] == "exchanged":
                    # Includes an exchange that committed while the CLI was disconnecting.
                    conn.execute(
                        "UPDATE account_cli_credentials SET revoked_at=%s WHERE authorization_id=%s",
                        (now, rid),
                    )
                    conn.execute(
                        "UPDATE cli_authorizations SET state='cancelled' WHERE id=%s",
                        (rid,),
                    )
                else:
                    conn.execute(
                        "UPDATE cli_authorizations SET state='cancelled' WHERE id=%s",
                        (rid,),
                    )
                return {"state": "cancelled"}
            if recover:
                if row["state"] == "cancelled":
                    return failure("credential_unavailable", 410)
                if row["state"] != "exchanged":
                    return failure("not_exchanged", 409)
                if now >= row["exchanged_at"] + timedelta(seconds=RECOVERY_TTL):
                    return failure("recovery_expired", 410)
                return self.issued(conn, row, verifier)
            if row["state"] == "exchanged":
                return failure("already_exchanged", 409)
            if row["state"] == "cancelled" or row["expires_at"] <= now:
                return failure("expired_or_cancelled", 410)
            if row["state"] != "approved":
                return failure("approval_required", 409)
            if row["code_expires_at"] <= now:
                return failure("code_expired", 410)
            if row["attempts"] >= 5:
                return failure("attempt_limit", 429)
            if not hmac.compare_digest(
                row["code_hash"],
                digest((code or "").replace("-", "").replace(" ", "").upper()),
            ):
                conn.execute(
                    "UPDATE cli_authorizations SET attempts=attempts+1 WHERE id=%s",
                    (rid,),
                )
                return failure("invalid_code", 400)
            conn.execute(
                """INSERT INTO account_cli_credentials
                (id,authorization_id,account_id,token_hash,created_at,expires_at) VALUES (%s,%s,%s,%s,%s,%s)""",
                (
                    uuid4(),
                    rid,
                    row["account_id"],
                    digest(self.token(rid, verifier)),
                    now,
                    now + timedelta(seconds=CREDENTIAL_TTL),
                ),
            )
            conn.execute(
                "UPDATE cli_authorizations SET state='exchanged', exchanged_at=%s WHERE id=%s",
                (now, rid),
            )
            return self.issued(conn, row, verifier)
