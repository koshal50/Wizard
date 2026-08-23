/**
 * ResultEvaluator — deterministic hypothesis evaluation. This is what keeps LLM
 * calls to a minimum: only genuinely UNEXPECTED results escalate. Every node type
 * has a fixed rule pinned here.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { evaluateNode } from "../src/runtime/ResultEvaluator.ts";
import type { InvestigationNode, Observation } from "../src/core/types.ts";

function node(action: InvestigationNode["action"], partial: Partial<InvestigationNode> = {}): InvestigationNode {
  return {
    nodeId: "node_001",
    type: action.type as InvestigationNode["type"],
    action,
    hypothesis: "h",
    dependencies: [],
    status: "running",
    createdAt: "2026-01-01T00:00:00.000Z",
    successClaim: { type: "T", value: "ok" },
    failureClaim: { type: "T", value: "bad" },
    ...partial,
  };
}

function obs(type: Observation["type"], data: Record<string, unknown>): Observation {
  return { observationId: "obs_001", nodeId: "node_001", type, data, createdAt: "t", immutable: true };
}

test("execute exit 0 → SUCCESS with successClaim", () => {
  const n = node({ type: "execute", command: "node -v" });
  const r = evaluateNode(n, obs("command_result", { exitCode: 0, timedOut: false }));
  assert.equal(r.outcome, "SUCCESS");
  assert.equal(r.claimTemplate?.value, "ok");
});

test("execute nonzero exit → FAILURE with failureClaim", () => {
  const n = node({ type: "execute", command: "node -v" });
  const r = evaluateNode(n, obs("command_result", { exitCode: 1, timedOut: false }));
  assert.equal(r.outcome, "FAILURE");
  assert.equal(r.reasonCode, "nonzero_exit");
  assert.equal(r.claimTemplate?.value, "bad");
});

test("execute timeout → UNEXPECTED", () => {
  const n = node({ type: "execute", command: "node -v" });
  const r = evaluateNode(n, obs("command_result", { exitCode: null, timedOut: true }));
  assert.equal(r.outcome, "UNEXPECTED");
  assert.equal(r.reasonCode, "timed_out");
});

test("execute with null exit + disabled marker → UNEXPECTED/execution_disabled", () => {
  const n = node({ type: "execute", command: "node -v" });
  const r = evaluateNode(n, obs("command_result", { exitCode: null, timedOut: false, stderr: "[execution disabled]" }));
  assert.equal(r.outcome, "UNEXPECTED");
  assert.equal(r.reasonCode, "execution_disabled");
});

test("read present → SUCCESS, missing → FAILURE", () => {
  const n = node({ type: "read", filePath: "a" });
  assert.equal(evaluateNode(n, obs("file_content", { exists: true })).outcome, "SUCCESS");
  assert.equal(evaluateNode(n, obs("file_content", { exists: false })).outcome, "FAILURE");
});

test("parse ok → SUCCESS, not ok → FAILURE", () => {
  const n = node({ type: "parse", sourceObservationId: "obs_000", parser: "json" });
  assert.equal(evaluateNode(n, obs("parse_result", { ok: true })).outcome, "SUCCESS");
  assert.equal(evaluateNode(n, obs("parse_result", { ok: false })).outcome, "FAILURE");
});

test("an error observation is always UNEXPECTED", () => {
  const n = node({ type: "read", filePath: "a" });
  const r = evaluateNode(n, obs("error", { message: "boom" }));
  assert.equal(r.outcome, "UNEXPECTED");
  assert.equal(r.reasonCode, "error");
});
