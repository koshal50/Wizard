/** Request-local accounting; stores only provider metadata, never model content. */
import { AsyncLocalStorage } from "node:async_hooks";
import { randomUUID } from "node:crypto";

export interface UsageEvent {
  event_id: string;
  provider: string;
  model: string;
  agent: string;
  provider_request_id: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  usage_source: "provider-reported" | "unavailable";
  accuracy: "exact" | "incomplete";
  created_at: string;
}

export const usageContext = new AsyncLocalStorage<UsageEvent[]>();
const count = (value: unknown): number | null =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0 ? value : null;

export function normalizeUsage(payload: unknown, provider: string): Pick<UsageEvent,
  "input_tokens" | "output_tokens" | "total_tokens" | "usage_source" | "accuracy"> {
  const usage = (payload as {usage?: Record<string, unknown>} | null)?.usage ?? {};
  let input = count(usage.prompt_tokens ?? usage.input_tokens);
  const output = count(usage.completion_tokens ?? usage.output_tokens);
  // Anthropic's input_tokens excludes cache reads and cache creation.
  if (provider === "anthropic" && input !== null) {
    for (const field of ["cache_read_input_tokens", "cache_creation_input_tokens"]) {
      if (usage[field] !== undefined) {
        const cached = count(usage[field]);
        input = cached === null || input === null ? null : input + cached;
      }
    }
  }
  const total = count(usage.total_tokens) ??
    (input !== null && output !== null ? input + output : null);
  return {input_tokens: input, output_tokens: output, total_tokens: total,
    usage_source: total === null ? "unavailable" : "provider-reported",
    accuracy: input !== null && output !== null && total !== null ? "exact" : "incomplete"};
}

export function recordUsage(payload: unknown, provider: string, model: string,
  requestId: string | null, agent: string, eventId = randomUUID()): void {
  usageContext.getStore()?.push({event_id: eventId, provider, model, agent,
    provider_request_id: requestId, created_at: new Date().toISOString(),
    ...normalizeUsage(payload, provider)});
}
