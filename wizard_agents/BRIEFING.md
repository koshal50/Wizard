# Agent System — Briefing & vLLM Handoff

## What was the brief

Review this branch (the "agent-system" branch, actual git name
`feature/wizard-agents`) as a read-only pass and report:

- Is the repo structure proper and as expected?
- Is anything repeated / duplicated?
- Why is `wizard-runtime-engine/` on this branch "just pycache, no code"?
- Does the repo adapt to **vLLM inference with an open-source model** — for
  both the Agent System and the Investigation Planner?

Constraint: the project has no budget for paid Claude/Anthropic models, so the
LLM must be a free, open-source model served locally.

## How vLLM is a good option for both the Planner and the Agent System

- **Free & self-hosted.** vLLM serves open-source models (Llama, Qwen,
  Mistral, etc.) on your own hardware — no per-token cost, which is the whole
  reason Claude/Anthropic is ruled out.
- **OpenAI-compatible.** vLLM exposes `POST /v1/chat/completions`. That means a
  single provider talking to a `base_url` works unchanged for **both**
  subsystems — one integration pattern, reused twice.
- **Drop-in by design.** The Agent System already isolates the LLM behind the
  `LLMProvider` ABC (`app/llm/base.py`) + `get_llm_provider()` factory. Swapping
  providers is config, not surgery — `ExplorerAgent` / `VerificationAgent` never
  change.
- **Structured output already solved.** The existing `AnthropicProvider` gets
  strict JSON by appending the target Pydantic model's JSON Schema to the system
  prompt, then `model_validate(...)`. The same trick works verbatim against
  vLLM — the model returns JSON, we validate it.
- **Offline / deterministic dev stays intact.** `mock` remains the default for
  tests and demos; vLLM becomes the real runtime provider.

## What was done

- Read-only review of the branch (structure, contracts, agents, providers,
  docs). Findings:
  - **No duplication.** The agents do **not** re-implement the engine.
    `adapters/runtime_adapter.py` defines only the boundary and defers all truth
    to Runtime; the contracts are propose-only; both `agent.py` files are thin
    (build prompt → `generate_structured` → validate → return).
  - **Engine "no code" explained.** `wizard-runtime-engine/` was never committed
    on this branch. On disk it is leftover `.venv/`, `.pytest_cache/`, `.wizard/`
    output, and orphaned `.pyc` (0 `.py` under `src/`). The engine source lives
    on other branches.
  - **Structure smells:** double-nested `wizard_agents/wizard_agents/`, ~40
    committed `__pycache__`/`.pyc` files, and no tracked `.gitignore`.
- Added a root `.gitignore` so `wizard-runtime-engine/`, virtualenvs, bytecode,
  caches, `.wizard/` output, and `.env` are never tracked/committed.

## What was expected to be done

The design expected a real, non-mock LLM provider so the agents could run
against an actual model. That provider was expected to be a free/open-source
model via vLLM (given the no-paid-models constraint). Instead the branch wires
only `mock` + `anthropic` (Claude = paid, disallowed), and the Investigation
Planner's own doc still lists its LLM provider as "undefined." So **vLLM is not
yet wired in either subsystem** — the abstraction is ready for it, but the
provider does not exist.

## What the owner should do now

Agent System:

1. Add `VLLMProvider(LLMProvider)` in `app/llm/` — mirror
   `anthropic_provider.py` (JSON-schema-in-system-prompt → `model_validate`).
   Use the already-installed `httpx` to POST to the vLLM `/v1/chat/completions`
   endpoint — **no new dependency needed**.
2. Add one `elif provider_name == "vllm":` branch in `factory.py`.
3. Add `.env` vars: `WIZARD_LLM_PROVIDER=vllm`, `WIZARD_LLM_BASE_URL=...`,
   `WIZARD_LLM_MODEL=<open-source-model>`; update `.env.example` and
   `docs/llm_configuration.md`. Drop the `anthropic` dep and the Claude default
   as dead weight.
4. Hygiene: untrack the ~40 committed `.pyc` (`git rm -r --cached` the
   `__pycache__` dirs — the new `.gitignore` alone does not remove
   already-committed files), and collapse the double-nested
   `wizard_agents/wizard_agents/`.

Investigation Planner:

5. Wire the same OpenAI-compatible vLLM `base_url` provider into the Planner so
   both subsystems share one open-source model. This is the identical gap.
