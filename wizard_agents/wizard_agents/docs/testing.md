# Testing

## Running the suite

```bash
pip install -r requirements.txt --break-system-packages   # if needed
pytest
```

`pytest.ini` sets `pythonpath = .` and `testpaths = tests`, so `pytest`
run from the repo root picks everything up automatically. All tests run
against `MockLLMProvider` — no network access or API key is required.

## Layout

| File | Covers |
|---|---|
| `tests/conftest.py` | Shared fixtures: mock LLM provider, sample `ExplorerInput`/`VerificationInput` for various scenarios |
| `tests/test_explorer.py` | Explorer unit tests |
| `tests/test_verification.py` | Verification unit tests |
| `tests/test_api.py` | FastAPI endpoint tests (`TestClient`) |
| `tests/test_integration.py` | Full pipeline tests (Explorer → mock Runtime → Verification) |
| `tests/fixtures/` | Standalone fixture-builder modules for named project scenarios |

## Explorer test coverage

- Valid node, multiple nodes, route handling (next_node)
- Available-tool selection / restricted tool sets
- Invalid tool rejected by semantic validation
- Malformed LLM response → `ExplorerAgentError`
- Missing required fields → rejected by Pydantic
- Failed previous action handled as context, not repeated blindly
- Next-node generation, including terminal (no next node) case
- Output validation: unknown `next_node`, over-budget step count,
  `command` without `execute_command`

## Verification test coverage

- Supported claim, weak claim (documentation-only), contradictory
  evidence, missing evidence, multiple claims in one call
- Unresolved-claim propagation for contradictions
- Malformed input rejected by Pydantic (`claims` requires ≥1 entry)
- Malformed LLM output → `VerificationAgentError`
- Hallucinated claim_id rejected by semantic validation
- Markdown report generation (starts with a heading, contains expected sections)
- Inconsistent finding states (supported + unresolved) rejected

## API test coverage

- `/health`
- `/explorer/investigate` success + validation error
- `/verification/verify` success + validation error

Tests override the `get_provider` FastAPI dependency to force
`MockLLMProvider`, independent of whatever `WIZARD_LLM_PROVIDER` is set
in the environment.

## Integration test coverage

`tests/test_integration.py` runs the full documented flow — Planner-like
input → Explorer → `ToolRequest` → `MockRuntimeExecutor` → Observation →
Claim → Verification → Assessment — plus dedicated runs of each fixture
scenario:

- **Python project** — standard entrypoint-detection flow
- **Node.js project** — restricted tool set
- **Missing dependency project** — Explorer given a failed previous
  action and asked to still produce a valid plan
- **Contradictory documentation project** — Verification correctly flags
  the contradiction and marks the claim unresolved
- **Failed execution project** — Explorer plans around a prior timeout;
  Verification flags the resulting evidence-less claim as missing/unresolved

## Latest run

```
33 passed
```

(See the final summary at the end of this conversation for the exact
command output.)
