/**
 * Provider factory — selects an LLMProvider from environment configuration.
 *
 * Selection order:
 *   1. Explicit `LLM_PROVIDER` env value: "heuristic" | "mock" | "anthropic" | "openai".
 *   2. Default: "heuristic" — the offline, deterministic, no-key provider. This
 *      guarantees the whole system runs with zero configuration and zero network.
 *
 * If a hosted provider is requested but its API key is absent, the factory falls
 * back to the heuristic provider and records a warning (it never crashes and
 * never blocks the investigation on missing credentials).
 *
 * SECURITY: API keys are read from the environment only, passed straight into
 * the adapter, and NEVER logged (only presence/absence is logged).
 */
import type { Logger } from "../util/logger.ts";
import type { LLMProvider } from "./LLMProvider.ts";
import { HeuristicLLMProvider } from "./providers/HeuristicLLMProvider.ts";
import { MockLLMProvider } from "./providers/MockLLMProvider.ts";
import { AnthropicLLMProvider } from "./providers/AnthropicLLMProvider.ts";
import { OpenAILLMProvider } from "./providers/OpenAILLMProvider.ts";

export type ProviderName = "heuristic" | "mock" | "anthropic" | "openai";

export interface ProviderEnv {
  LLM_PROVIDER?: string;
  LLM_MODEL?: string;
  ANTHROPIC_API_KEY?: string;
  OPENAI_API_KEY?: string;
}

export interface ProviderFactoryOptions {
  env?: ProviderEnv;
  logger?: Logger;
}

function normalize(name: string | undefined): ProviderName {
  const n = (name ?? "").trim().toLowerCase();
  if (n === "anthropic" || n === "openai" || n === "mock" || n === "heuristic") return n;
  return "heuristic";
}

export function createProviderFromEnv(opts: ProviderFactoryOptions = {}): LLMProvider {
  const env = opts.env ?? (process.env as ProviderEnv);
  const requested = normalize(env.LLM_PROVIDER);
  const log = opts.logger;

  if (requested === "anthropic") {
    const apiKey = env.ANTHROPIC_API_KEY ?? "";
    if (!apiKey) {
      log?.warn("llm.provider.fallback", { requested: "anthropic", reason: "missing ANTHROPIC_API_KEY", using: "heuristic" });
      return new HeuristicLLMProvider();
    }
    log?.info("llm.provider.selected", { provider: "anthropic", keyPresent: true });
    return new AnthropicLLMProvider({ apiKey, model: env.LLM_MODEL });
  }

  if (requested === "openai") {
    const apiKey = env.OPENAI_API_KEY ?? "";
    if (!apiKey) {
      log?.warn("llm.provider.fallback", { requested: "openai", reason: "missing OPENAI_API_KEY", using: "heuristic" });
      return new HeuristicLLMProvider();
    }
    log?.info("llm.provider.selected", { provider: "openai", keyPresent: true });
    return new OpenAILLMProvider({ apiKey, model: env.LLM_MODEL });
  }

  if (requested === "mock") {
    log?.info("llm.provider.selected", { provider: "mock" });
    return new MockLLMProvider();
  }

  log?.info("llm.provider.selected", { provider: "heuristic" });
  return new HeuristicLLMProvider();
}
