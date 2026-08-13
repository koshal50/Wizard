# Wizard Agent System

Implements the **Explorer Agent** and **Verification Agent** subsystem
of the Wizard architecture. Agents reason; Runtime executes. This
subsystem never touches the repository, sandbox, or Claims Graph
directly — it consumes structured input and produces validated,
structured output over REST/JSON.

Built independently from any other Wizard component, with clean
Pydantic contracts as the integration surface for the Investigation
Planner and Runtime Engine (built separately by other developers).

## Quick start

```bash
pip install -r requirements.txt --break-system-packages   # or without the flag, depending on your environment
cp .env.example .env        # defaults to mock mode, no API key needed
pytest                      # 33 tests, all offline
python examples/end_to_end_example.py
uvicorn app.api.main:app --reload   # http://localhost:8000/docs
```

## Stack

Python, FastAPI, Pydantic, pytest, REST/JSON, Markdown, and a small LLM
provider abstraction (`MockLLMProvider` for offline/dev, `AnthropicProvider`
for production). No vector database, LangChain, or orchestration
framework — the agents are stateless request/response transformations.

## Documentation

| Doc | Covers |
|---|---|
| [`docs/architecture.md`](docs/architecture.md) | Where this fits in Wizard, core principle, component map |
| [`docs/explorer.md`](docs/explorer.md) | Explorer Agent contract and rules |
| [`docs/verification.md`](docs/verification.md) | Verification Agent contract and rules |
| [`docs/api.md`](docs/api.md) | REST endpoints, request/response examples |
| [`docs/runtime_integration.md`](docs/runtime_integration.md) | Exact contract for the Runtime Engine developer |
| [`docs/llm_configuration.md`](docs/llm_configuration.md) | Switching between mock and real LLM providers |
| [`docs/testing.md`](docs/testing.md) | Test layout and coverage |
| [`docs/setup.md`](docs/setup.md) | Local install/run instructions |
| [`docs/example_workflow.md`](docs/example_workflow.md) | Walkthrough of `examples/end_to_end_example.py` |

## Project structure

```
wizard_agents/
  app/
    contracts/      Pydantic schemas (the integration surface)
    llm/             LLMProvider abstraction, mock + Anthropic providers
    prompts/         System/user prompt templates
    validation/       Semantic validation beyond Pydantic parsing
    explorer/        ExplorerAgent + tool registry
    verification/     VerificationAgent
    api/             FastAPI app + routes
    adapters/        RuntimeExecutor interface + MockRuntimeExecutor (tests only)
  tests/
    fixtures/        Named project scenarios (python, nodejs, missing dep, etc.)
    test_explorer.py
    test_verification.py
    test_api.py
    test_integration.py
  examples/
    end_to_end_example.py
  docs/
  requirements.txt
  .env.example
```

## Core principle

**Agents reason. Runtime executes.**

Explorer produces a validated Tool Request / Execution Plan; it never
calls a tool. Verification produces a structured assessment; it never
modifies the Claims Graph or trust. Both are enforced by semantic
validation on every LLM response, not just by convention.
