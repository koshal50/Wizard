/**
 * CLI argument parsing + exit-code policy. Pure functions, no process spawning —
 * the composition root's decision logic is unit-tested here; the full run is
 * covered by endToEnd.test.ts.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { parseArgs, exitCodeFor } from "../src/cli/wizard.ts";
import type { InvestigationResult } from "../src/core/types.ts";

test("parses intent + targets + path positionally", () => {
  const { positionals } = parseArgs(["verify", "runtime", "dependencies", "./repo"]);
  assert.deepEqual(positionals, ["verify", "runtime", "dependencies", "./repo"]);
});

test("parses flags with values (space and = forms)", () => {
  const { flags } = parseArgs(["./repo", "--budget", "40", "--provider=mock", "--no-exec"]);
  assert.equal(flags.budget, 40);
  assert.equal(flags.provider, "mock");
  assert.equal(flags.noExec, true);
});

test("--json and --help are booleans", () => {
  const { flags } = parseArgs(["--json", "--help"]);
  assert.equal(flags.json, true);
  assert.equal(flags.help, true);
});

test("unknown flags are ignored rather than crashing", () => {
  const { flags, positionals } = parseArgs(["./repo", "--totally-unknown"]);
  assert.deepEqual(positionals, ["./repo"]);
  assert.equal(flags.help, false);
});

function result(state: InvestigationResult["state"], satisfied: number, total: number): InvestigationResult {
  return {
    investigationId: "inv",
    state,
    technologyPlan: null,
    investigationGraph: { nodes: [], edges: [] },
    knowledgeGraph: { claims: [], relationships: [] },
    observations: [],
    claims: [],
    goals: [],
    statistics: { nodesExecuted: 0, plannerCalls: 0, claimsCreated: 0, observationsCreated: 0, goalsSatisfied: satisfied, goalsTotal: total },
    terminationReason: "x",
  };
}

test("exit code 2 when the engine failed", () => {
  assert.equal(exitCodeFor(result("failed", 0, 0), "verify"), 2);
});

test("exit code 1 when a verify run left goals unsatisfied", () => {
  assert.equal(exitCodeFor(result("completed", 1, 2), "verify"), 1);
});

test("exit code 0 when a verify run satisfied all goals", () => {
  assert.equal(exitCodeFor(result("completed", 2, 2), "verify"), 0);
});

test("non-verify intents do not fail on unsatisfied goals", () => {
  assert.equal(exitCodeFor(result("completed", 0, 3), "investigate"), 0);
});
