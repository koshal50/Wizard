/**
 * End-to-end investigation — the checklist's "end-to-end investigation works".
 *
 * Runs the REAL RuntimeEngine against the sample fixture using the offline
 * heuristic provider (zero network, zero API key). Asserts the whole lifecycle:
 * scan → manifest → technology plan → goals → node execution → observations →
 * evidence → claims → trust → goal satisfaction → report.
 *
 * Determinism: ids + clock are injected fixed. Execution is REAL (`node
 * --version`), which is safe and available wherever these tests run.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { RuntimeEngine } from "../src/runtime/RuntimeEngine.ts";
import { InvestigationPlanner } from "../src/planner/InvestigationPlanner.ts";
import { HeuristicLLMProvider } from "../src/llm/providers/HeuristicLLMProvider.ts";
import { ReportGenerator } from "../src/report/ReportGenerator.ts";
import { createIdFactory } from "../src/util/ids.ts";
import { fixedClock } from "../src/util/clock.ts";
import { nullLogger } from "../src/util/logger.ts";
import type { InvestigationRequest } from "../src/core/types.ts";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIXTURE = path.resolve(HERE, "../sample-repos/sample-node-project");

function makeEngine() {
  const logger = nullLogger();
  const planner = new InvestigationPlanner(new HeuristicLLMProvider(), logger);
  return new RuntimeEngine({ planner, logger, clock: fixedClock(), ids: createIdFactory() });
}

function request(overrides: Partial<InvestigationRequest> = {}): InvestigationRequest {
  return {
    investigationId: "inv_001",
    userIntent: "verify",
    repositoryPath: FIXTURE,
    investigationTargets: ["runtime", "dependencies"],
    budget: { maxNodeExecutions: 60, executionsUsed: 0, maxPlannerCalls: 25, plannerCallsUsed: 0, maxExecutionTimeMs: 120000 },
    configuration: { allowExecution: true, persist: false, goalTrustThreshold: 0.6 },
    ...overrides,
  };
}

test("offline heuristic run satisfies runtime + dependency goals", async () => {
  const result = await makeEngine().run(request());

  assert.equal(result.state, "completed");
  assert.equal(result.terminationReason, "all goals resolved");
  assert.equal(result.statistics.goalsTotal, 2);
  assert.equal(result.statistics.goalsSatisfied, 2);

  // Technology plan detected Node.js.
  const techNames = (result.technologyPlan?.technologies ?? []).map((t) => t.name);
  assert.ok(techNames.includes("Node.js"), `expected Node.js in ${techNames.join(",")}`);
});

test("produces a high-trust, execution-backed RUNTIME_STATUS claim with provenance", async () => {
  const result = await makeEngine().run(request());
  const runtime = result.claims.find((c) => c.type === "RUNTIME_STATUS");
  assert.ok(runtime, "expected a RUNTIME_STATUS claim");
  assert.equal(runtime!.value, "verified");
  assert.ok(runtime!.trust >= 0.85, `expected high trust, got ${runtime!.trust}`);
  assert.equal(runtime!.status, "asserted");
  // provenance points back to a real node + observation that exist in the result
  const obsIds = new Set(result.observations.map((o) => o.observationId));
  const nodeIds = new Set(result.investigationGraph.nodes.map((n) => n.nodeId));
  assert.ok(obsIds.has(runtime!.provenance.observationId));
  assert.ok(nodeIds.has(runtime!.provenance.sourceNodeId));
});

test("parses the dependency manifest (MANIFEST_PARSED)", async () => {
  const result = await makeEngine().run(request());
  const manifest = result.claims.find((c) => c.type === "MANIFEST_PARSED");
  assert.ok(manifest, "expected a MANIFEST_PARSED claim");
  assert.equal(manifest!.status, "asserted");
});

test("the two graphs stay separate: no claim leaks into the investigation graph", async () => {
  const result = await makeEngine().run(request());
  for (const node of result.investigationGraph.nodes) {
    assert.ok(!("trust" in node), "investigation nodes must not carry trust");
    assert.ok(!("evidence" in node), "investigation nodes must not carry evidence");
  }
  // claims only ever appear in the knowledge graph
  assert.ok(result.knowledgeGraph.claims.length >= 2);
});

test("with execution disabled, the runtime goal is honestly unsatisfiable (not fabricated)", async () => {
  const result = await makeEngine().run(
    request({ configuration: { allowExecution: false, persist: false, goalTrustThreshold: 0.6 } }),
  );
  const runtimeGoal = result.goals.find((g) => g.name === "Verify Runtime");
  assert.ok(runtimeGoal);
  assert.equal(runtimeGoal!.status, "unsatisfiable");
  // and no fabricated verified runtime claim
  const runtime = result.claims.find((c) => c.type === "RUNTIME_STATUS" && c.value === "verified");
  assert.equal(runtime, undefined);
});

test("the run is reproducible: same inputs → same ids, claims, and trust", async () => {
  const a = await makeEngine().run(request());
  const b = await makeEngine().run(request());
  const shape = (r: Awaited<ReturnType<RuntimeEngine["run"]>>) =>
    r.claims.map((c) => `${c.claimId}:${c.type}=${c.value}@${c.trust.toFixed(3)}`).sort();
  assert.deepEqual(shape(a), shape(b));
});

test("the result renders to a Markdown report without throwing", async () => {
  const result = await makeEngine().run(request());
  const md = new ReportGenerator().render(result, { generatedAt: "2026-01-01T00:00:00.000Z" });
  assert.match(md, /Goals satisfied \| 2 \/ 2/);
  assert.match(md, /RUNTIME_STATUS/);
});
