/**
 * AnthropicLLMProvider — real hosted-model adapter (Claude Messages API).
 *
 * Uses the global `fetch` (Node 18+). The API key is injected via config, never
 * read from a hard-coded constant and never logged. On any transport/HTTP/parse
 * failure it returns `llmErr` rather than throwing, so the Runtime degrades to a
 * recorded failure instead of crashing. Model output is JSON-extracted then
 * schema-validated before it is returned.
 */
import type { Schema } from "../../validation/schema.ts";
import { safeParse } from "../../validation/schema.ts";
import type { LLMProvider, LLMRequest, LLMResult } from "../LLMProvider.ts";
import { llmErr, llmOk } from "../LLMProvider.ts";
import { extractJson } from "../extractJson.ts";

type FetchLike = (input: string, init: RequestInit) => Promise<Response>;

export interface AnthropicConfig {
  apiKey: string;
  model?: string;
  baseUrl?: string;
  anthropicVersion?: string;
  /** Injectable for tests; defaults to global fetch. */
  fetchImpl?: FetchLike;
  /** Per-request timeout. Default 60s. */
  timeoutMs?: number;
}

const DEFAULT_MODEL = "claude-sonnet-5";
const DEFAULT_BASE_URL = "https://api.anthropic.com";
const DEFAULT_VERSION = "2023-06-01";

export class AnthropicLLMProvider implements LLMProvider {
  readonly name = "anthropic";
  private readonly cfg: Required<Omit<AnthropicConfig, "fetchImpl">> & { fetchImpl: FetchLike };

  constructor(config: AnthropicConfig) {
    this.cfg = {
      apiKey: config.apiKey,
      model: config.model ?? DEFAULT_MODEL,
      baseUrl: config.baseUrl ?? DEFAULT_BASE_URL,
      anthropicVersion: config.anthropicVersion ?? DEFAULT_VERSION,
      timeoutMs: config.timeoutMs ?? 60000,
      fetchImpl: config.fetchImpl ?? ((globalThis.fetch as unknown) as FetchLike),
    };
  }

  async generateStructured<T>(request: LLMRequest, schema: Schema<T>): Promise<LLMResult<T>> {
    if (!this.cfg.apiKey) return llmErr<T>(["anthropic: missing API key"], "", this.name);

    const body = {
      model: this.cfg.model,
      max_tokens: request.maxTokens ?? 2048,
      temperature: request.temperature ?? 0,
      system: request.system,
      messages: [{ role: "user", content: request.prompt }],
    };

    let response: Response;
    try {
      response = await this.cfg.fetchImpl(`${this.cfg.baseUrl}/v1/messages`, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          "x-api-key": this.cfg.apiKey,
          "anthropic-version": this.cfg.anthropicVersion,
        },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(this.cfg.timeoutMs),
      });
    } catch (e) {
      return llmErr<T>([`anthropic: request failed: ${(e as Error).message}`], "", this.name);
    }

    if (!response.ok) {
      const text = await safeText(response);
      return llmErr<T>([`anthropic: HTTP ${response.status}`], text, this.name);
    }

    const payload = (await safeJson(response)) as
      | { content?: Array<{ type?: string; text?: string }> }
      | null;
    const text = payload?.content?.find((c) => c.type === "text")?.text ?? "";
    if (!text) return llmErr<T>(["anthropic: empty completion"], JSON.stringify(payload), this.name);

    const extracted = extractJson(text);
    if (!extracted.ok) return llmErr<T>([extracted.error], text, this.name);

    const parsed = safeParse(schema, extracted.value);
    if (!parsed.ok) return llmErr<T>(parsed.errors, text, this.name);
    return llmOk<T>(parsed.value, text, this.name);
  }
}

async function safeText(res: Response): Promise<string> {
  try {
    return await res.text();
  } catch {
    return "";
  }
}

async function safeJson(res: Response): Promise<unknown> {
  try {
    return await res.json();
  } catch {
    return null;
  }
}
