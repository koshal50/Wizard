/**
 * MockLLMProvider — deterministic, queue-driven provider for tests.
 *
 * Per the design (spec §55 "MOCK LLM"):
 *   - `queueResponse(value)` enqueues the next structured value to return.
 *   - `queueRaw(text)` enqueues raw model text (exercises JSON extraction).
 *   - It tracks: number of calls, the requests it received, and what it returned.
 *
 * If nothing is queued, it fails (rather than inventing output) so tests that
 * expected ZERO LLM calls fail loudly if the code path calls the model.
 */
import type { Schema } from "../../validation/schema.ts";
import { safeParse } from "../../validation/schema.ts";
import type { LLMProvider, LLMRequest, LLMResult } from "../LLMProvider.ts";
import { llmErr, llmOk } from "../LLMProvider.ts";
import { extractJson } from "../extractJson.ts";

type QueuedItem =
  | { kind: "value"; value: unknown }
  | { kind: "raw"; text: string }
  | { kind: "error"; message: string };

export interface MockCallRecord {
  request: LLMRequest;
  provider: string;
}

export class MockLLMProvider implements LLMProvider {
  readonly name = "mock";
  private queue: QueuedItem[] = [];
  private readonly callLog: MockCallRecord[] = [];
  private readonly returned: unknown[] = [];

  /** Enqueue a structured value; it is re-serialized so schema validation runs. */
  queueResponse(value: unknown): this {
    this.queue.push({ kind: "value", value });
    return this;
  }

  /** Enqueue raw text (e.g. JSON wrapped in prose) to exercise extraction. */
  queueRaw(text: string): this {
    this.queue.push({ kind: "raw", text });
    return this;
  }

  /** Enqueue a provider-level failure. */
  queueError(message: string): this {
    this.queue.push({ kind: "error", message });
    return this;
  }

  get callCount(): number {
    return this.callLog.length;
  }

  calls(): MockCallRecord[] {
    return this.callLog.slice();
  }

  lastRequest(): LLMRequest | undefined {
    return this.callLog.at(-1)?.request;
  }

  responses(): unknown[] {
    return this.returned.slice();
  }

  async generateStructured<T>(request: LLMRequest, schema: Schema<T>): Promise<LLMResult<T>> {
    this.callLog.push({ request, provider: this.name });
    const item = this.queue.shift();
    if (!item) {
      return llmErr<T>(["MockLLMProvider: no response queued for this call"], "", this.name);
    }
    if (item.kind === "error") {
      return llmErr<T>([`MockLLMProvider: ${item.message}`], "", this.name);
    }

    const raw = item.kind === "raw" ? item.text : JSON.stringify(item.value);
    const extracted = extractJson(raw);
    if (!extracted.ok) return llmErr<T>([extracted.error], raw, this.name);

    const parsed = safeParse(schema, extracted.value);
    if (!parsed.ok) return llmErr<T>(parsed.errors, raw, this.name);

    this.returned.push(parsed.value);
    return llmOk<T>(parsed.value, raw, this.name);
  }
}
