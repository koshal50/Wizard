# LLM Configuration

## Provider selection

Set via the `WIZARD_LLM_PROVIDER` environment variable:

| Value | Provider | Requires API key |
|---|---|---|
| `mock` (default) | `MockLLMProvider` | No |
| `anthropic` | `AnthropicProvider` | Yes (`ANTHROPIC_API_KEY`) |

Selection happens in `app/llm/factory.py::get_llm_provider()`, used by
both the API layer (`app/api/deps.py`) and can be called directly by
other code.

## Running in mock mode (default, no key required)

```bash
# .env or shell
WIZARD_LLM_PROVIDER=mock
```

`MockLLMProvider` (`app/llm/mock_provider.py`) is fully deterministic: it
builds `ExplorerOutput` / `VerificationOutput` directly from the
structured input rather than parsing free text, using simple heuristics
(prefer `read_file` if available; flag contradicted/missing/
documentation-only claims). This is what the entire test suite and the
example script run against, so the whole system — API, agents,
validation — is exercisable and demonstrable with zero external
dependencies.

## Running with a real LLM

```bash
# .env
WIZARD_LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
WIZARD_LLM_MODEL=claude-sonnet-4-6   # optional, this is the default
```

`AnthropicProvider` (`app/llm/anthropic_provider.py`) calls the Anthropic
Messages API, instructing the model (via the system prompt plus the
target Pydantic model's JSON Schema) to return only a JSON object
matching the schema. The response is parsed and validated with
`response_model.model_validate(...)`; any parse or validation failure
raises `LLMError`, which the agent layer turns into an
`ExplorerAgentError` / `VerificationAgentError`.

The API key is read from the environment only — it is never hard-coded,
and `AnthropicProvider.__init__` fails fast with a clear message if it's
missing.

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

Then add a branch in `app/llm/factory.py::get_llm_provider()`. No agent
code changes are required — `ExplorerAgent` and `VerificationAgent` only
depend on the `LLMProvider` interface.
