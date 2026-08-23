/**
 * LLM provider abstraction.
 *
 * The Planner is provider-agnostic: it builds an `LLMRequest` + a validation
 * `Schema<T>`, calls `generateStructured`, and receives a *validated* `T` back.
 * Whether that value was produced by a real hosted model (Anthropic / OpenAI),
 * a deterministic offline heuristic, or a queued mock is opaque to the caller.
 *
 * Two channels travel with every request:
 *   - `prompt` / `system`: natural-language text, consumed by real LLM adapters.
 *   - `context`: a structured payload consumed by the deterministic heuristic
 *     provider (and ignored by real adapters). This lets the exact same Planner
 *     code path run fully offline with no API key.
 *
 * SECURITY: whatever a provider returns is UNTRUSTED. `generateStructured`
 * always runs the model output through the supplied schema before returning it,
 * so a caller that receives `{ ok: true }` is guaranteed a well-formed `T`.
 */
import type { Schema } from "../validation/schema.ts";

/** What the caller is asking the model to produce. Drives heuristic dispatch. */
export type LLMPurpose = "technology_plan" | "ongoing_plan" | "escalation";

export interface LLMRequest {
  purpose: LLMPurpose;
  /** System / role instruction for real LLM adapters. */
  system?: string;
  /** The user-facing prompt text for real LLM adapters. */
  prompt: string;
  /**
   * Structured, trusted payload built by the Planner. The heuristic provider
   * reads this to produce deterministic output. Real adapters ignore it (they
   * work from `prompt`). Never contains secrets.
   */
  context?: Record<string, unknown>;
  maxTokens?: number;
  temperature?: number;
}

export type LLMResult<T> =
  | { ok: true; value: T; raw: string; provider: string }
  | { ok: false; errors: string[]; raw: string; provider: string };

export interface LLMProvider {
  /** Stable identifier for logs / the audit trail, e.g. "heuristic". */
  readonly name: string;
  generateStructured<T>(request: LLMRequest, schema: Schema<T>): Promise<LLMResult<T>>;
}

export function llmOk<T>(value: T, raw: string, provider: string): LLMResult<T> {
  return { ok: true, value, raw, provider };
}

export function llmErr<T>(errors: string[], raw: string, provider: string): LLMResult<T> {
  return { ok: false, errors, raw, provider };
}
