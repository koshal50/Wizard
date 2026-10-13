"""One optional PostgreSQL pool, short transactions, metadata-only accounting."""

from __future__ import annotations

import os
from pathlib import Path


def database_url():
    """Same local configuration for supervised and directly started runtimes."""
    if "WIZARD_DATABASE_URL" in os.environ:
        return os.environ["WIZARD_DATABASE_URL"].strip() or None
    from dotenv import dotenv_values

    engine = Path(__file__).resolve().parents[3]
    candidates = [Path.cwd() / ".env", engine / ".env", engine.parent / ".env"]
    for path in dict.fromkeys(candidates):
        value = next(
            (
                value
                for key, value in dotenv_values(path).items()
                if key.upper() == "WIZARD_DATABASE_URL" and value
            ),
            None,
        )
        if value:
            return value
    return None


TOTALS = """
COALESCE(SUM(e.input_tokens) FILTER (WHERE e.usage_source='provider-reported'), 0)::bigint AS input_tokens,
COALESCE(SUM(e.output_tokens) FILTER (WHERE e.usage_source='provider-reported'), 0)::bigint AS output_tokens,
COALESCE(SUM(e.total_tokens) FILTER (WHERE e.usage_source='provider-reported'), 0)::bigint AS total_tokens,
COUNT(e.event_id)::bigint AS llm_calls,
COALESCE(BOOL_OR(e.accuracy != 'exact' OR e.usage_source != 'provider-reported'), false) OR
COALESCE(BOOL_OR(r.incomplete), false) AS incomplete
"""


class UsageDatabase:
    def __init__(self, url: str):
        from psycopg.conninfo import conninfo_to_dict
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool

        options = conninfo_to_dict(url).get("options", "") + " -c statement_timeout=3000"
        self.pool = ConnectionPool(
            url,
            min_size=0,
            max_size=4,
            timeout=2,
            open=True,
            kwargs={"row_factory": dict_row, "connect_timeout": 2, "options": options},
        )

    def close(self):
        self.pool.close()

    def recover(self, profile, before=None):
        from datetime import UTC, datetime

        before = before or datetime.now(UTC)
        with self.pool.connection() as conn:
            conn.execute(
                """UPDATE wizard_runs r SET pending_requests=0, incomplete=true,
                status=CASE WHEN finished_at IS NULL THEN 'incomplete' ELSE status END,
                finished_at=COALESCE(finished_at, now()), revision=revision+1
                FROM wizard_sessions s WHERE r.session_id=s.session_id AND s.profile_id=%s
                AND r.started_at < %s
                AND (r.finished_at IS NULL OR r.pending_requests>0)""",
                (profile, before),
            )

    def persist(self, job: dict):
        run = job["run"]
        with self.pool.connection() as conn:
            conn.execute(
                """INSERT INTO wizard_sessions(session_id, profile_id)
                VALUES (%s, %s) ON CONFLICT(session_id) DO UPDATE SET updated_at=now()
                WHERE wizard_sessions.profile_id=EXCLUDED.profile_id""",
                (run["session_id"], run["profile_id"]),
            )
            owner = conn.execute(
                "SELECT profile_id FROM wizard_sessions WHERE session_id=%s", (run["session_id"],)
            ).fetchone()
            if owner["profile_id"] != run["profile_id"]:
                raise ValueError("Usage session ownership mismatch")
            conn.execute(
                """INSERT INTO wizard_runs(run_id, session_id, command, status,
                started_at, finished_at, revision, pending_requests, incomplete)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(run_id) DO UPDATE SET status=EXCLUDED.status,
                finished_at=EXCLUDED.finished_at, revision=EXCLUDED.revision,
                pending_requests=EXCLUDED.pending_requests,
                incomplete=wizard_runs.incomplete OR EXCLUDED.incomplete
                WHERE wizard_runs.session_id=EXCLUDED.session_id
                AND wizard_runs.revision <= EXCLUDED.revision""",
                tuple(
                    run[k]
                    for k in (
                        "run_id",
                        "session_id",
                        "command",
                        "status",
                        "started_at",
                        "finished_at",
                        "revision",
                        "pending_requests",
                        "incomplete",
                    )
                ),
            )
            saved = conn.execute(
                "SELECT session_id FROM wizard_runs WHERE run_id=%s", (run["run_id"],)
            ).fetchone()
            if saved["session_id"] != run["session_id"]:
                raise ValueError("Usage run ownership mismatch")
            for event in job.get("events", []):
                conn.execute(
                    """INSERT INTO token_usage_events(event_id, run_id, provider, model,
                    agent, provider_request_id, input_tokens, output_tokens, total_tokens,
                    usage_source, accuracy, created_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT DO NOTHING""",
                    (
                        event["event_id"],
                        run["run_id"],
                        *(
                            event.get(k)
                            for k in (
                                "provider",
                                "model",
                                "agent",
                                "provider_request_id",
                                "input_tokens",
                                "output_tokens",
                                "total_tokens",
                                "usage_source",
                                "accuracy",
                                "created_at",
                            )
                        ),
                    ),
                )
                # A final provider snapshot replaces an unknown/provisional one.
                # Duplicate delivery of an exact response cannot increase totals.
                if event["accuracy"] == "exact":
                    conn.execute(
                        """UPDATE token_usage_events SET input_tokens=%s,
                        output_tokens=%s, total_tokens=%s, usage_source=%s, accuracy=%s
                        WHERE run_id=%s AND accuracy!='exact' AND (event_id=%s OR
                        (provider=%s AND model=%s AND provider_request_id=%s))""",
                        (
                            event["input_tokens"],
                            event["output_tokens"],
                            event["total_tokens"],
                            event["usage_source"],
                            event["accuracy"],
                            run["run_id"],
                            event["event_id"],
                            event["provider"],
                            event["model"],
                            event["provider_request_id"],
                        ),
                    )

    def run(self, profile: str, run_id: str) -> dict | None:
        with self.pool.connection() as conn:
            return self._run(conn, profile, run_id)

    @staticmethod
    def _run(conn, profile, run_id):
        result = conn.execute(
            f"""SELECT r.*, s.profile_id, {TOTALS}
                FROM wizard_runs r JOIN wizard_sessions s USING(session_id)
                LEFT JOIN token_usage_events e USING(run_id)
                WHERE r.run_id=%s AND s.profile_id=%s GROUP BY r.run_id, s.profile_id""",
            (run_id, profile),
        ).fetchone()
        if result:
            for key in ("started_at", "finished_at"):
                result[key] = result[key].isoformat() if result[key] else None
        return result

    def overall(self, profile: str, session_id: str | None = None) -> dict:
        where = "s.profile_id=%s"
        params = [profile]
        if session_id:
            where += " AND s.session_id=%s"
            params.append(session_id)
        with self.pool.connection() as conn:
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            totals = conn.execute(
                f"""SELECT {TOTALS} FROM wizard_sessions s
                JOIN wizard_runs r USING(session_id) LEFT JOIN token_usage_events e USING(run_id)
                WHERE {where}""",
                params,
            ).fetchone()
            rows = conn.execute(
                f"""SELECT r.command, {TOTALS} FROM wizard_sessions s
                JOIN wizard_runs r USING(session_id) LEFT JOIN token_usage_events e USING(run_id)
                WHERE {where} GROUP BY r.command""",
                params,
            ).fetchall()
            latest = conn.execute(
                f"""SELECT r.run_id FROM wizard_runs r
                JOIN wizard_sessions s USING(session_id) WHERE {where}
                ORDER BY r.started_at DESC, r.run_id DESC LIMIT 1""",
                params,
            ).fetchone()
            current = self._run(conn, profile, latest["run_id"]) if latest else None
        return {
            "scope": "local-profile",
            "profile_id": profile,
            "session_id": session_id,
            "totals": totals,
            "by_command": {row.pop("command"): row for row in rows},
            "current_run": current,
        }


def migrate(url: str):
    """Explicit operator action; runtime startup never runs schema changes."""
    import psycopg

    sql = (Path(__file__).parent / "migrations" / "001_token_usage.sql").read_text("utf-8")
    with psycopg.connect(url, connect_timeout=5) as conn:
        conn.execute("SELECT pg_advisory_xact_lock(873461052)")
        conn.execute(sql)


if __name__ == "__main__":
    url = database_url()
    if not url:
        raise SystemExit("Set WIZARD_DATABASE_URL before applying the usage migration")
    try:
        migrate(url)
    except Exception as exc:  # noqa: BLE001 -- never expose connection credentials in CLI errors
        raise SystemExit(
            f"Usage migration failed ({type(exc).__name__}); check connection and schema"
        ) from None
    print("Usage migration applied")
