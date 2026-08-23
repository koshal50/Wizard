/**
 * PlannerValidator — the SEMANTIC/security gate on top of the schema. Type/action
 * consistency, path confinement, command allowlist, exec-disabled, and budget
 * truncation. Bad proposals are DROPPED, not mutated, so a partly-bad batch still
 * yields its safe subset.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { validateParsedBatch } from "../src/planner/PlannerValidator.ts";
import type { PlannerNodeBatch } from "../src/core/types.ts";

const ROOT = process.platform === "win32" ? "C:\\repo" : "/repo";
const opts = { repoRoot: ROOT, budgetRemaining: 10, allowExecution: true };

function batch(nodes: PlannerNodeBatch["nodes"]): PlannerNodeBatch {
  return { nodes };
}

test("accepts a well-formed read proposal", () => {
  const r = validateParsedBatch(
    batch([{ type: "read", action: { type: "read", filePath: "src/a.ts" }, hypothesis: "h" }]),
    opts,
  );
  assert.equal(r.accepted.length, 1);
  assert.equal(r.rejected.length, 0);
});

test("rejects node whose type does not match its action type", () => {
  const r = validateParsedBatch(
    batch([{ type: "read", action: { type: "execute", command: "node -v" }, hypothesis: "h" }]),
    opts,
  );
  assert.equal(r.accepted.length, 0);
  assert.match(r.rejected[0]!.reason, /does not match action type/);
});

test("rejects a read that escapes the repo", () => {
  const r = validateParsedBatch(
    batch([{ type: "read", action: { type: "read", filePath: "../etc/passwd" }, hypothesis: "h" }]),
    opts,
  );
  assert.equal(r.accepted.length, 0);
  assert.match(r.rejected[0]!.reason, /unsafe read path/);
});

test("rejects an unsafe command", () => {
  const r = validateParsedBatch(
    batch([{ type: "execute", action: { type: "execute", command: "rm -rf /" }, hypothesis: "h" }]),
    opts,
  );
  assert.equal(r.accepted.length, 0);
  assert.match(r.rejected[0]!.reason, /unsafe command/);
});

test("rejects execute proposals when execution is disabled", () => {
  const r = validateParsedBatch(
    batch([{ type: "execute", action: { type: "execute", command: "node -v" }, hypothesis: "h" }]),
    { ...opts, allowExecution: false },
  );
  assert.equal(r.accepted.length, 0);
  assert.match(r.rejected[0]!.reason, /execution disabled/);
});

test("keeps the safe subset of a partly-bad batch", () => {
  const r = validateParsedBatch(
    batch([
      { type: "read", action: { type: "read", filePath: "ok.txt" }, hypothesis: "h" },
      { type: "read", action: { type: "read", filePath: "../bad" }, hypothesis: "h" },
    ]),
    opts,
  );
  assert.equal(r.accepted.length, 1);
  assert.equal(r.rejected.length, 1);
});

test("truncates a batch to the remaining node budget", () => {
  const r = validateParsedBatch(
    batch([
      { type: "read", action: { type: "read", filePath: "a" }, hypothesis: "h" },
      { type: "read", action: { type: "read", filePath: "b" }, hypothesis: "h" },
      { type: "read", action: { type: "read", filePath: "c" }, hypothesis: "h" },
    ]),
    { ...opts, budgetRemaining: 2 },
  );
  assert.equal(r.accepted.length, 2);
  assert.equal(r.rejected.length, 1);
  assert.match(r.rejected[0]!.reason, /budget/);
});
