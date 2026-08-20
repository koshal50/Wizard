/**
 * Planner-output schemas — the SHAPE gate for untrusted LLM output. The critical
 * property: runtime-owned fields (status, createdAt, observationId, trust) are
 * REJECTED, so the Planner can never smuggle them in.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { safeParse } from "../src/validation/schema.ts";
import { plannerNodeProposalSchema, plannerNodeBatchSchema } from "../src/planner/schemas.ts";

test("a valid read proposal parses", () => {
  const r = safeParse(plannerNodeProposalSchema, {
    type: "read",
    action: { type: "read", filePath: "package.json" },
    hypothesis: "exists",
  });
  assert.equal(r.ok, true);
});

test("a proposal carrying a runtime-owned status is rejected", () => {
  const r = safeParse(plannerNodeProposalSchema, {
    type: "read",
    action: { type: "read", filePath: "package.json" },
    hypothesis: "exists",
    status: "complete",
  });
  assert.equal(r.ok, false);
});

test("smuggled createdAt / observationId / trust are all rejected", () => {
  for (const extra of [{ createdAt: "x" }, { observationId: "obs_1" }, { trust: 1 }]) {
    const r = safeParse(plannerNodeProposalSchema, {
      type: "read",
      action: { type: "read", filePath: "a" },
      hypothesis: "h",
      ...extra,
    });
    assert.equal(r.ok, false, `expected rejection for ${JSON.stringify(extra)}`);
  }
});

test("an action with the wrong shape for its discriminator is rejected", () => {
  const r = safeParse(plannerNodeProposalSchema, {
    type: "execute",
    action: { type: "execute" }, // missing required command
    hypothesis: "h",
  });
  assert.equal(r.ok, false);
});

test("a batch of nodes with a rationale parses", () => {
  const r = safeParse(plannerNodeBatchSchema, {
    nodes: [{ type: "read", action: { type: "read", filePath: "a" }, hypothesis: "h" }],
    rationale: "test",
  });
  assert.equal(r.ok, true);
});
