/**
 * EvidenceEngine — the ONLY writer of claims. This exercises the full provenance
 * pipeline end to end at the unit level:
 *   Observation → Evidence (source-kind weight) → Claim → Trust → Knowledge Graph
 * and pins the two invariants the architecture cares about most:
 *   - the Planner's trustWeight hint is metadata only (ignored by trust),
 *   - contradicting evidence for the same claim type flips it to contested/refuted.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { EvidenceEngine } from "../src/evidence/EvidenceEngine.ts";
import { ClaimStore } from "../src/claims/ClaimStore.ts";
import { KnowledgeGraph } from "../src/graphs/KnowledgeGraph.ts";
import { createIdFactory } from "../src/util/ids.ts";
import { fixedClock } from "../src/util/clock.ts";
import { nullLogger } from "../src/util/logger.ts";
import type { ClaimTemplate, Observation } from "../src/core/types.ts";

function engine() {
  const claims = new ClaimStore();
  const knowledge = new KnowledgeGraph();
  const ev = new EvidenceEngine({
    claims,
    knowledge,
    ids: createIdFactory(),
    clock: fixedClock(),
    logger: nullLogger(),
    investigationId: "inv_001",
  });
  return { ev, claims, knowledge };
}

function obs(id: string, type: Observation["type"], data: Record<string, unknown>): Observation {
  return { observationId: id, nodeId: "node_001", type, data, createdAt: "t", immutable: true };
}

test("execution evidence records a high-trust asserted claim with provenance", () => {
  const { ev, knowledge } = engine();
  const tpl: ClaimTemplate = { type: "RUNTIME_STATUS", value: "verified", trustWeight: 0.5 };
  const claim = ev.recordClaim(tpl, obs("obs_001", "command_result", { exitCode: 0 }), "node_001");

  assert.equal(claim.type, "RUNTIME_STATUS");
  assert.equal(claim.value, "verified");
  assert.equal(Number(claim.trust.toFixed(2)), 0.9); // execution weight, NOT the 0.5 hint
  assert.equal(claim.status, "asserted");
  assert.equal(claim.provenance.sourceNodeId, "node_001");
  assert.equal(claim.provenance.observationId, "obs_001");
  // written through to the Knowledge Graph
  assert.equal(knowledge.claimsOfType("RUNTIME_STATUS").length, 1);
});

test("the Planner trustWeight hint never becomes the trust score", () => {
  const { ev } = engine();
  // A wildly optimistic hint on weak (parse) evidence must not inflate trust.
  const tpl: ClaimTemplate = { type: "MANIFEST_PARSED", value: "package.json", trustWeight: 1 };
  const claim = ev.recordClaim(tpl, obs("obs_001", "parse_result", { ok: true }), "node_001");
  assert.equal(Number(claim.trust.toFixed(2)), 0.7); // structured_file weight, not 1.0
});

test("corroborating evidence merges into one claim and raises trust", () => {
  const { ev, claims } = engine();
  const tpl: ClaimTemplate = { type: "X", value: "v" };
  ev.recordClaim(tpl, obs("obs_001", "parse_result", { ok: true }), "n1");
  const claim = ev.recordClaim(tpl, obs("obs_002", "parse_result", { ok: true }), "n2");
  assert.equal(claims.size(), 1); // merged, not duplicated
  assert.equal(claim.evidence.length, 2);
  assert.ok(claim.trust > 0.7); // noisy-OR of two 0.7s
  assert.equal(claim.provenanceHistory.length, 2);
});

test("contradicting evidence for the same type contests the claim", () => {
  const { ev } = engine();
  ev.recordClaim({ type: "RUNTIME_STATUS", value: "verified" }, obs("obs_001", "parse_result", { ok: true }), "n1");
  const claim = ev.recordClaim(
    { type: "RUNTIME_STATUS", value: "broken" },
    obs("obs_002", "command_result", { exitCode: 1 }),
    "n2",
  );
  // The engine adopts the best-supported value: execution(broken)=0.9 beats
  // structured_file(verified)=0.7, so value flips to "broken". Because that
  // winning value's own support (0.9) still exceeds its contradiction (0.7),
  // the claim is CONTESTED, not refuted — a best-supported value can never be
  // refuted in a two-way contest, only contested.
  assert.equal(claim.value, "broken");
  assert.equal(claim.status, "contested");
});

test("recording the same observation twice is idempotent", () => {
  const { ev } = engine();
  const o = obs("obs_001", "parse_result", { ok: true });
  ev.recordClaim({ type: "X", value: "v" }, o, "n1");
  const claim = ev.recordClaim({ type: "X", value: "v" }, o, "n1");
  assert.equal(claim.evidence.length, 1); // not double-counted
});
