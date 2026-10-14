import { test } from "node:test";
import assert from "node:assert/strict";
import { normalizeUsage, recordUsage, usageContext, type UsageEvent } from "../src/llm/usage.ts";
import { OpenAILLMProvider } from "../src/llm/providers/OpenAILLMProvider.ts";
import { AnthropicLLMProvider } from "../src/llm/providers/AnthropicLLMProvider.ts";
import { technologyPlanSchema } from "../src/planner/schemas.ts";
import { deadlineContext } from "../src/llm/deadline.ts";

test("OpenAI normalization preserves provider total and missing breakdown", () => {
  assert.deepEqual(normalizeUsage({usage: {total_tokens: 42}}, "openai"), {
    input_tokens: null, output_tokens: null, total_tokens: 42,
    usage_source: "provider-reported", accuracy: "incomplete"});
  assert.equal(normalizeUsage({usage: {prompt_tokens: -1}}, "openai").total_tokens, null);
});

test("Anthropic includes cached input without double counting output", () => {
  const result = normalizeUsage({usage: {input_tokens: 10, output_tokens: 4,
    cache_read_input_tokens: 20, cache_creation_input_tokens: 30}}, "anthropic");
  assert.equal(result.input_tokens, 60);
  assert.equal(result.total_tokens, 64);
  assert.equal(result.accuracy, "exact");
});

test("concurrent request collectors do not share events", async () => {
  const collect = (model: string) => usageContext.run([], async () => {
    await Promise.resolve();
    recordUsage(null, "fixture", model, null, "fixture");
    return usageContext.getStore()!;
  });
  const [a, b] = await Promise.all([collect("a"), collect("b")]);
  assert.equal(a.length, 1);
  assert.equal(b.length, 1);
  assert.equal(a[0]!.model, "a");
  assert.equal(b[0]!.model, "b");
  assert.notEqual(a[0]!.event_id, b[0]!.event_id);
});

for (const kind of ["openai", "anthropic"] as const) {
  test(`${kind} captures usage even when model output fails validation`, async () => {
    const body = kind === "openai"
      ? {choices: [{message: {content: "invalid"}}], usage: {prompt_tokens: 20, completion_tokens: 5}}
      : {content: [{type: "text", text: "invalid"}], usage: {input_tokens: 20, output_tokens: 5}};
    const config = {apiKey: "fixture", model: "fixture", fetchImpl: async () =>
      new Response(JSON.stringify(body), {headers: {"x-request-id": "req-1"}})};
    const provider = kind === "openai" ? new OpenAILLMProvider(config) : new AnthropicLLMProvider(config);
    const events: UsageEvent[] = [];
    const result = await usageContext.run(events, () => provider.generateStructured(
      {purpose: "technology_plan", prompt: "secret prompt"}, technologyPlanSchema));
    assert.equal(result.ok, false);
    assert.equal(events.length, 1);
    assert.equal(events[0]!.total_tokens, 25);
    assert.equal(events[0]!.provider_request_id, "req-1");
    assert.ok(!JSON.stringify(events).includes("secret prompt"));
  });
}

test("an expired deadline before transport is not counted as a model request", async () => {
  const events: UsageEvent[] = [];
  let requests = 0;
  const provider = new OpenAILLMProvider({apiKey: "fixture", fetchImpl: async () => {
    requests++;
    throw new Error("must not be called");
  }});
  await usageContext.run(events, () => deadlineContext.run(Date.now() - 1,
    () => provider.generateStructured({purpose: "technology_plan", prompt: "fixture"}, technologyPlanSchema)));
  assert.equal(requests, 0);
  assert.equal(events.length, 0);
});
