"""Explicit account DB configuration; never falls back to a developer's runtime DB."""

import os
from pathlib import Path

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool


class Database:
    def __init__(self, url):
        from psycopg.conninfo import conninfo_to_dict

        options = (
            conninfo_to_dict(url).get("options", "") + " -c statement_timeout=5000"
        )
        self.pool = ConnectionPool(
            url,
            min_size=0,
            max_size=8,
            timeout=3,
            open=True,
            kwargs={"row_factory": dict_row, "connect_timeout": 3, "options": options},
        )

    def connection(self):
        return self.pool.connection()

    def close(self):
        self.pool.close()


ACCOUNT_TABLES = (
    "website_accounts",
    "website_sessions",
    "cli_authorizations",
    "account_cli_credentials",
    "account_rate_limits",
    "website_oidc_attempts",
    "website_oidc_identities",
)


def missing_account_tables(url):
    """Read-only preflight in the configured account database/search path."""
    import psycopg

    with psycopg.connect(url, connect_timeout=3) as conn:
        conn.read_only = True
        conn.execute("SET LOCAL statement_timeout = '5s'")
        rows = conn.execute(
            "SELECT name FROM unnest(%s::text[]) AS required(name) "
            "WHERE to_regclass(name) IS NULL ORDER BY name",
            (list(ACCOUNT_TABLES),),
        ).fetchall()
    return [row[0] for row in rows]


def migrate(url):
    import psycopg

    with psycopg.connect(url) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(752894011)")
        conn.execute(
            (
                Path(__file__).parent / "migrations/001_account_authorization.sql"
            ).read_text()
        )


def cleanup(url):
    """Retain terminal requests for one day; never delete live credentials."""
    import psycopg

    with psycopg.connect(url) as conn:
        conn.execute("DELETE FROM website_oidc_attempts WHERE expires_at < now()")
        conn.execute(
            "DELETE FROM account_rate_limits WHERE starts_at < now() - interval '1 day'"
        )
        conn.execute(
            "DELETE FROM account_cli_credentials WHERE expires_at < now() - interval '1 day' "
            "OR revoked_at < now() - interval '1 day'"
        )
        conn.execute(
            "DELETE FROM cli_authorizations a WHERE a.expires_at < now() - interval '1 day' "
            "AND NOT EXISTS (SELECT 1 FROM account_cli_credentials c WHERE c.authorization_id=a.id)"
        )
        # Sessions referenced by live credentials must survive cascading cleanup.
        conn.execute(
            "DELETE FROM website_sessions s WHERE s.expires_at < now() - interval '1 day' "
            "AND NOT EXISTS (SELECT 1 FROM cli_authorizations a WHERE a.browser_session_id=s.id)"
        )


if __name__ == "__main__":
    import sys

    url = os.environ.get("WIZARD_ACCOUNT_DATABASE_URL")
    if not url:
        raise SystemExit("Set WIZARD_ACCOUNT_DATABASE_URL to the account database")
    try:
        if sys.argv[1:] == ["check"]:
            missing = missing_account_tables(url)
            if missing:
                raise SystemExit(
                    "Account tables missing: "
                    + ", ".join(missing)
                    + ". Run python -m backend.db against this account database."
                )
            print("All seven account tables are present")
        elif sys.argv[1:] == ["cleanup"]:
            cleanup(url)
        elif not sys.argv[1:]:
            migrate(url)
        else:
            raise SystemExit("Usage: python -m backend.db [check|cleanup]")
    except Exception:  # noqa: BLE001 -- never expose DSN credentials in migration failures
        raise SystemExit(
            "Account database operation failed; check connectivity, privileges, and schema"
        ) from None
    print("Account database operation completed")
