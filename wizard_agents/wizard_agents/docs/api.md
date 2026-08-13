# API

FastAPI app defined in `app/api/main.py`. Run locally with:

```bash
uvicorn app.api.main:app --reload
```

Interactive docs (Swagger UI) are then available at `http://localhost:8000/docs`.

## `GET /health`

Returns service status and the currently configured LLM provider.

**Response `200`**
```json
{ "status": "ok", "llm_provider": "mock" }
```

## `POST /explorer/investigate`

**Request body**: `ExplorerInput` (see `docs/explorer.md`)

**Response `200`**: `ExplorerOutput`

**Response `422`**: validation error — either the request body didn't
match `ExplorerInput` (FastAPI/Pydantic-level), or the agent produced
output that failed semantic validation, or the LLM call itself failed.
In all 422 cases the response body's `detail` explains why.

Example request:
```json
{
  "investigation_id": "inv-1",
  "current_node": { "node_id": "identify_application_entrypoint", "goal": "Find the entrypoint" },
  "route": { "node_order": ["identify_application_entrypoint"], "current_index": 0 },
  "nodes": [{ "node_id": "identify_application_entrypoint", "goal": "Find the entrypoint" }]
}
```

## `POST /verification/verify`

**Request body**: `VerificationInput` (see `docs/verification.md`)

**Response `200`**: `VerificationOutput`

**Response `422`**: validation error, same categories as above.

Example request:
```json
{
  "investigation_id": "inv-1",
  "claims": [
    {
      "claim_id": "c1",
      "statement": "The entrypoint is main.py",
      "evidence": [
        { "evidence_id": "e1", "description": "python main.py starts the server", "source": "execution", "supports_claim": true }
      ]
    }
  ]
}
```

## Error format

All agent-level failures (LLM error or semantic validation failure) are
returned as FastAPI's standard error shape:

```json
{ "detail": "Explorer output failed validation: selected_tool 'execute_command' is not in available_tools [...]" }
```

Malformed request bodies that don't match the Pydantic schema at all
return FastAPI's default validation error shape (a list of field-level
errors under `detail`).
