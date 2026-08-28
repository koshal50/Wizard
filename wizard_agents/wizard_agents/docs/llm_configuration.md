# LLM Configuration

## Provider selection

Set via the `WIZARD_LLM_PROVIDER` environment variable:

| Value | Provider | Requires a server |
|---|---|---|
| `mock` (default) | `MockLLMProvider` | No — tests / offline / deterministic dev |
| `vllm` | `VLLMProvider` | Yes — a self-hosted vLLM instance (real runtime) |

Selection happens in `app/llm/factory.py::get_llm_provider()`, used by the
API layer (`app/api/deps.py`) and callable directly by other code (e.g. the
Investigation Planner). Because agents depend only on the `LLMProvider`
interface, switching providers is configuration, not code.

## Running in mock mode (default, no server required)

```bash
WIZARD_LLM_PROVIDER=mock
```

`MockLLMProvider` (`app/llm/mock_provider.py`) is fully deterministic: it
builds `ExplorerOutput` / `VerificationOutput` directly from the structured
input rather than parsing free text. The entire test suite and the example
script run against it, so the whole system is exercisable with zero external
dependencies.

## Running with a real, open-source LLM via vLLM

vLLM serves open-source models (Llama, Qwen, Mistral, …) on your own hardware
and exposes an **OpenAI-compatible** `POST /v1/chat/completions` endpoint — no
per-token cost, no API key.

```bash
# .env
WIZARD_LLM_PROVIDER=vllm
WIZARD_LLM_BASE_URL=http://localhost:8000   # vLLM default port
WIZARD_LLM_MODEL=Qwen/Qwen2.5-7B-Instruct   # any model your vLLM serves
```

Start a server, for example:

```bash
python -m vllm.entrypoints.openai.api_server --model Qwen/Qwen2.5-7B-Instruct
```

`VLLMProvider` (`app/llm/vllm_provider.py`) uses the already-installed `httpx`
to POST to `{WIZARD_LLM_BASE_URL}/v1/chat/completions`. It enforces structure
by appending the target Pydantic model's JSON Schema to the system prompt (and
requesting `response_format=json_object`), then validates the response with
`response_model.model_validate(...)`. Any parse or validation failure raises
`LLMError`, which the agent layer turns into `ExplorerAgentError` /
`VerificationAgentError`. No secrets are hard-coded — all configuration comes
from the environment.

The same `WIZARD_LLM_BASE_URL` / `WIZARD_LLM_MODEL` configuration is intended to
be shared by the Investigation Planner, so both subsystems use one open-source
model behind one integration pattern.

## Adding another provider

Implement `LLMProvider` (`app/llm/base.py`):

```python
class LLMProvider(ABC):
    @abstractmethod
    def generate_structured(self, system_prompt, user_prompt, response_model, *, max_tokens=2000, temperature=0.0, metadata=None) -> T: ...

    @property
    @abstractmethod
    def name(self) -> str: ...
```

Then add a branch in `app/llm/factory.py::get_llm_provider()`. No agent code
changes are required — `ExplorerAgent` and `VerificationAgent` only depend on
the `LLMProvider` interface.
