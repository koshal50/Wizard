/**
 * TrustEngine — the deterministic trust math is the backbone of "the Planner does
 * not set trust". These tests pin the noisy-OR combination, contradiction, and
 * status derivation.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { computeTrust } from "../src/trust/TrustEngine.ts";
import type { Evidence } from "../src/core/types.ts";

function ev(weight: number, attestedValue: string): Evidence {
  return {
    observationId: "obs",
    nodeId: "node",
    polarity: "supporting",
    sourceKind: "execution",
    weight,
    attestedValue,
  };
}

test("single supporting evidence yields its weight as trust, status asserted", () => {
  const r = computeTrust("verified", [ev(0.9, "verified")]);
  assert.equal(Number(r.trust.toFixed(2)), 0.9);
  assert.equal(r.status, "asserted");
});

test("corroborating evidence combines by noisy-OR (raises but never reaches 1)", () => {
  const r = computeTrust("verified", [ev(0.7, "verified"), ev(0.7, "verified")]);
  assert.equal(Number(r.trust.toFixed(2)), 0.91); // 1 - 0.3*0.3
  assert.ok(r.trust < 1);
  assert.equal(r.status, "asserted");
});

test("stronger contradiction refutes the claim and drives trust down", () => {
  const r = computeTrust("verified", [ev(0.4, "verified"), ev(0.9, "broken")]);
  assert.equal(r.status, "refuted");
  assert.ok(r.trust < 0.1);
});

test("equal support and contradiction is contested", () => {
  const r = computeTrust("verified", [ev(0.7, "verified"), ev(0.7, "broken")]);
  assert.equal(r.status, "contested");
});

test("trust is a pure function of evidence weights (no external channel)", () => {
  const a = computeTrust("v", [ev(0.7, "v")]);
  const b = computeTrust("v", [ev(0.7, "v")]);
  assert.deepEqual(a, b);
});
