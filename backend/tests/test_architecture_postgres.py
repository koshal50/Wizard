from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import Settings
from backend.tests.test_architecture_contract import graph
from backend.tests.test_authorization_postgres import approved, exchange


def credential(client):
    rid, verifier, code = approved(client)
    response = exchange(client, rid, verifier, code)
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.json()["access_token"]}


def test_postgres_save_reopen_ownership_limits_and_revocation(client, database, clock):
    assert client.post("/api/investigations", json=graph()).status_code == 401
    assert client.get("/api/investigations").status_code == 401
    headers = credential(client)
    # Browser authentication alone never authorizes a CLI upload.
    assert client.post("/api/investigations", json=graph()).status_code == 401
    response = client.post("/api/investigations", json=graph(), headers=headers)
    assert response.status_code == 201, response.text
    public_id = response.json()["investigation_id"]
    with database.connection() as conn:
        row = conn.execute("SELECT * FROM architecture_investigations WHERE id=%s", (public_id,)).fetchone()
        assert row["graph"]["evidence"][0]["line_start"] == 4
        assert row["graph"]["nodes"][0]["label"] == "API"
        assert row["schema_version"] == 1 and row["owner_id"]
    # New backend process/app uses the committed PostgreSQL document.
    with TestClient(create_app(Settings("unused", "http://localhost", b"x" * 32, True), database, clock), base_url="http://localhost") as reopened:
        result = reopened.get("/api/investigations/" + public_id, headers=headers)
        assert result.status_code == 200 and result.json()["graph"] == row["graph"]
        assert reopened.get("/api/investigations/" + public_id).status_code == 401
    assert client.get("/api/investigations/" + public_id).status_code == 200
    assert client.get("/api/investigations").json()["investigations"][0]["id"] == public_id
    with database.connection() as conn:
        other = uuid4()
        conn.execute("INSERT INTO website_accounts(id,email,full_name) VALUES(%s,%s,%s)", (other, "other@example.test", "Other"))
        conn.execute("UPDATE architecture_investigations SET owner_id=%s WHERE id=%s", (other, public_id))
    assert client.get("/api/investigations/" + public_id, headers=headers).status_code == 404
    assert client.get("/api/investigations/" + public_id).status_code == 404
    assert client.get("/api/investigations").json() == {"investigations": []}
    malformed = graph()
    malformed["relationships"][0]["source"] = "unknown"
    assert client.post("/api/investigations", json=malformed, headers=headers).status_code == 422
    assert client.post("/api/investigations", content="x" * 2_000_001, headers=headers).status_code == 413
    assert client.delete("/api/account/credential", headers=headers).status_code == 200
    assert client.get("/api/investigations/" + public_id, headers=headers).status_code == 401
    assert client.post("/api/investigations", json=graph(), headers=headers).status_code == 401


def test_database_failure_never_acknowledges_a_save(client, database):
    headers = credential(client)
    with database.connection() as conn:
        conn.execute("ALTER TABLE architecture_investigations RENAME TO unavailable_architecture_investigations")
    response = client.post("/api/investigations", json=graph(), headers=headers)
    assert response.status_code == 503
    assert response.json() == {"error": "service_unavailable"}


def test_grouped_document_is_identical_after_postgres_and_authorized_api(client, database):
    from backend.architecture import ArchitectureGraph
    from backend.tests.test_architecture_contract import grouped_graph
    headers = credential(client)
    expected = ArchitectureGraph.model_validate(grouped_graph()).model_dump()
    response = client.post('/api/investigations', json=expected, headers=headers)
    assert response.status_code == 201
    public_id = response.json()['investigation_id']
    with database.connection() as conn:
        persisted = conn.execute('SELECT graph FROM architecture_investigations WHERE id=%s', (public_id,)).fetchone()['graph']
    assert persisted == expected
    assert client.get('/api/investigations/' + public_id, headers=headers).json()['graph'] == persisted
