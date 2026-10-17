"""Opt-in real PostgreSQL tests; only a generated, isolated schema is removed."""

import os
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import Settings
from backend.db import Database, migrate


@pytest.fixture
def database():
    url = os.environ.get("WIZARD_ACCOUNT_TEST_DATABASE_URL")
    if not url:
        pytest.skip(
            "Set WIZARD_ACCOUNT_TEST_DATABASE_URL for real PostgreSQL account tests"
        )
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import make_conninfo

    name = "wizard_account_test_" + uuid4().hex
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(name)))
    scoped = make_conninfo(url, options="-c search_path=" + name)
    db = None
    try:
        migrate(scoped)
        migrate(scoped)
        db = Database(scoped)
        with db.connection() as conn:
            assert (
                conn.execute("SELECT current_schema() AS name").fetchone()["name"]
                == name
            )
        yield db
    finally:
        if db:
            db.close()
        # This name is created above; no developer schema/data can be removed.
        assert name.startswith("wizard_account_test_") and len(name) == 52
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(name)))


@pytest.fixture
def clock():
    class Clock:
        now = datetime.now(UTC)

        def __call__(self):
            return self.now

    return Clock()


@pytest.fixture
def client(database, clock):
    app = create_app(
        Settings("unused", "http://localhost", b"x" * 32, True), database, clock
    )
    with TestClient(app, base_url="http://localhost") as client:
        yield client
