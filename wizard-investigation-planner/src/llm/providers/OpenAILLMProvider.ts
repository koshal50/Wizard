/**
 * OpenAILLMProvider — real hosted-model adapter (Chat Completions API).
 *
 * Same contract as the Anthropic adapter: injected key (never logged), global
 * `fetch` by default, `llmErr` instead of throwing, JSON-extract + schema
 * validate before returning. Uses `response_format: json_object` to nudge the
 * model toward pure JSON, but still runs extraction defensively.
 */
import type { Schema } from "../../validation/schema.ts";
import { safeParse } from "../../validation/schema.ts";
import type { LLMProvider, LLMRequest, LLMResult } from "../LLMProvider.ts";
import { llmErr, llmOk } from "../LLMProvider.ts";
import { extractJson } from "../extractJson.ts";

type FetchLike = (input: string, init: RequestInit) => Promise<Response>;

export interface OpenAIConfig {
  apiKey: string;
  model?: string;
  baseUrl?: string;
  fetchImpl?: FetchLike;
  timeoutMs?: number;
}

const DEFAULT_MODEL = "gpt-4o-mini";
const DEFAULT_BASE_URL = "https://api.openai.com";

export class OpenAILLMProvider implements LLMProvider {
  readonly name = "openai";
  private readonly cfg: Required<Omit<OpenAIConfig, "fetchImpl">> & { fetchImpl: FetchLike };

  constructor(config: OpenAIConfig) {
    this.cfg = {
      apiKey: config.apiKey,
      model: config.model ?? DEFAULT_MODEL,
      baseUrl: config.baseUrl ?? DEFAULT_BASE_URL,
      timeoutMs: config.timeoutMs ?? 60000,
      fetchImpl: config.fetchImpl ?? ((globalThis.fetch as unknown) as FetchLike),
    };
  }

  async generateStructured<T>(request: LLMRequest, schema: Schema<T>): Promise<LLMResult<T>> {
    if (!this.cfg.apiKey) return llmErr<T>(["openai: missing API key"], "", this.name);

    const messages = [
      ...(request.system ? [{ role: "system", content: request.system }] : []),
      { role: "user", content: request.prompt },
    ];
    const body = {
      model: this.cfg.model,
      temperature: request.temperature ?? 0,
      max_tokens: request.maxTokens ?? 2048,
      response_format: { type: "json_object" },
      messages,
    };

    let response: Response;
    try {
      response = await this.cfg.fetchImpl(`${this.cfg.baseUrl}/v1/chat/completions`, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          authorization: `Bearer ${this.cfg.apiKey}`,
        },
        body: JSON.stringify(body),
        signal: AbortSignal.timeout(this.cfg.timeoutMs),
      });
    } catch (e) {
      return llmErr<T>([`openai: request failed: ${(e as Error).message}`], "", this.name);
    }

    if (!response.ok) {
      const text = await safeText(response);
      return llmErr<T>([`openai: HTTP ${response.status}`], text, this.name);
    }

    const payload = (await safeJson(response)) as
      | { choices?: Array<{ message?: { content?: string } }> }
      | null;
    const text = payload?.choices?.[0]?.message?.content ?? "";
    if (!text) return llmErr<T>(["openai: empty completion"], JSON.stringify(payload), this.name);

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
