"""Opt-in disposable PostgreSQL fixture for the website's diagram browser tests.

Uses the existing backend app; never migrates the normal account schema.
"""
import argparse
import json
import os
from pathlib import Path
from uuid import uuid4

import psycopg
import uvicorn
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import make_conninfo

from backend.app import create_app
from backend.architecture import ArchitectureGraph
from backend.config import Settings
from backend.db import Database, migrate
from backend.tests import test_authorization_postgres as authorization


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, required=True)
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--origin", default="http://localhost:3000")
    args = parser.parse_args()
    url = os.environ.get("WIZARD_ACCOUNT_TEST_DATABASE_URL")
    if not url:
        parser.error("Set WIZARD_ACCOUNT_TEST_DATABASE_URL to a disposable test database")
    graph = ArchitectureGraph.model_validate_json(args.graph.read_bytes()).model_dump()
    if args.context.exists():
        parser.error("Context file already exists; choose a new fixture context path")
    name = "wizard_diagram_browser_" + uuid4().hex
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(name)))
    scoped = make_conninfo(url, options="-c search_path=" + name)
    database = None
    created_context = False
    try:
        migrate(scoped)
        database = Database(scoped)
        app = create_app(Settings(scoped, args.origin, os.urandom(32), True), database)
        authorization.ORIGIN = {"Origin": args.origin}
        with TestClient(app, base_url=args.origin) as client:
            rid, verifier, code = authorization.approved(client)
            token = authorization.exchange(client, rid, verifier, code).json()["access_token"]
            response = client.post("/api/investigations", json=graph, headers={"Authorization": "Bearer " + token})
            response.raise_for_status()
            args.context.parent.mkdir(parents=True, exist_ok=True)
            # This contains only short-lived credentials in the disposable schema.
            descriptor = os.open(args.context, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            created_context = True
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump({"id": response.json()["investigation_id"], "schema": name, "cookie": client.cookies.get("wizard_site"),
                           "graph": graph, "token": "Bearer " + token}, handle)
        print(f"Disposable diagram fixture ready on port {args.port}; Ctrl+C removes its schema and context.", flush=True)
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    finally:
        if created_context:
            args.context.unlink(missing_ok=True)
        if database:
            database.close()
        assert name.startswith("wizard_diagram_browser_") and len(name) == 55
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(name)))


if __name__ == "__main__":
    main()
