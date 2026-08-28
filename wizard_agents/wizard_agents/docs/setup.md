# Local Setup

## Requirements

- Python 3.10+

## Install

```bash
git clone <this repo>
cd wizard_agents
pip install -r requirements.txt
# On systems with an externally-managed Python (e.g. recent Debian/Ubuntu):
pip install -r requirements.txt --break-system-packages
```

## Configure

```bash
cp .env.example .env
```

Defaults to `WIZARD_LLM_PROVIDER=mock`, which requires no further
configuration. To use a real LLM, set `WIZARD_LLM_PROVIDER=vllm` with
`WIZARD_LLM_BASE_URL` and `WIZARD_LLM_MODEL` — see `docs/llm_configuration.md`.

## Run the API

```bash
uvicorn app.api.main:app --reload
```

Then visit `http://localhost:8000/docs` for interactive Swagger UI, or:

```bash
curl http://localhost:8000/health
```

## Run the tests

```bash
pytest
```

## Run the example end-to-end workflow

```bash
python examples/end_to_end_example.py
```

This runs the full Explorer → mock Runtime → Verification pipeline
offline and writes `examples/verification_report.md`.
