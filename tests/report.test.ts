/**
 * ReportGenerator — renders an InvestigationResult to Markdown. Two things matter:
 *   1. the report is faithful (goals, claims+trust+provenance, both graphs), and
 *   2. it NEVER leaks raw file contents / command stdout (secret-safety §26).
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { ReportGenerator } from "../src/report/ReportGenerator.ts";
import type { InvestigationResult } from "../src/core/types.ts";

function sampleResult(): InvestigationResult {
  const createdAt = "2026-01-01T00:00:00.000Z";
  return {
    investigationId: "inv_001",
    state: "completed",
    technologyPlan: {
      technologies: [
        { name: "Node.js", confidence: "high", signals: ["manifest: package.json"], initialGoals: ["Verify Runtime"], priorityFiles: ["package.json"] },
      ],
    },
    investigationGraph: {
      nodes: [
        {
          nodeId: "node_001",
          type: "execute",
          action: { type: "execute", command: "node --version" },
          hypothesis: "node works",
          successClaim: { type: "RUNTIME_STATUS", value: "verified" },
          dependencies: [],
          status: "complete",
          createdAt,
        },
      ],
      edges: [],
    },
    knowledgeGraph: {
      claims: [
        {
          claimId: "claim_001",
          type: "RUNTIME_STATUS",
          value: "verified",
          trust: 0.9,
          status: "asserted",
          evidence: [{ observationId: "obs_001", nodeId: "node_001", polarity: "supporting", sourceKind: "execution", weight: 0.9, attestedValue: "verified" }],
          provenance: { sourceNodeId: "node_001", observationId: "obs_001", investigationId: "inv_001" },
          provenanceHistory: [{ sourceNodeId: "node_001", observationId: "obs_001", investigationId: "inv_001" }],
          createdAt,
          updatedAt: createdAt,
        },
      ],
      relationships: [],
    },
    observations: [
      {
        observationId: "obs_001",
        nodeId: "node_001",
        type: "command_result",
        data: {
          command: "node --version",
          workingDirectory: ".",
          exitCode: 0,
          stdout: "v24.15.0 SECRET_TOKEN_sk-must-not-appear",
          stderr: "",
          timedOut: false,
          durationMs: 12,
        },
        createdAt,
        immutable: true,
      },
    ],
    claims: [],
    goals: [
      {
        goalId: "goal_001",
        name: "Verify Runtime",
        technology: "Node.js",
        status: "satisfied",
        requirements: [{ claimType: "RUNTIME_STATUS", notValue: "broken", minTrust: 0.6, description: "runtime works" }],
      },
    ],
    statistics: { nodesExecuted: 1, plannerCalls: 1, claimsCreated: 1, observationsCreated: 1, goalsSatisfied: 1, goalsTotal: 1 },
    terminationReason: "all goals resolved",
  };
}

test("renders the core sections and the claim with trust + provenance", () => {
  const md = new ReportGenerator().render(sampleResult(), { generatedAt: "2026-01-01T00:00:00.000Z" });
  assert.match(md, /# Investigation Report/);
  assert.match(md, /Goals satisfied \| 1 \/ 1/);
  assert.match(md, /Verify Runtime/);
  assert.match(md, /RUNTIME_STATUS/);
  assert.match(md, /0\.90/); // trust
  assert.match(md, /`node_001` \/ `obs_001`/); // provenance cell
  assert.match(md, /Knowledge Graph — What We Know/);
  assert.match(md, /Investigation Graph — How We Found It/);
});

test("does NOT leak raw command stdout / secrets into the report", () => {
  const md = new ReportGenerator().render(sampleResult());
  assert.ok(!md.includes("SECRET_TOKEN"), "raw stdout must not appear in the report");
  assert.ok(!md.includes("sk-must-not-appear"), "secret-looking token must not appear");
  // it should still summarise the command result compactly
  assert.match(md, /`node --version` exit=0/);
});

test("render is deterministic for the same input", () => {
  const gen = new ReportGenerator();
  const opts = { generatedAt: "2026-01-01T00:00:00.000Z" };
  assert.equal(gen.render(sampleResult(), opts), gen.render(sampleResult(), opts));
});

test("empty-ish result still renders without throwing", () => {
  const empty: InvestigationResult = {
    investigationId: "inv_x",
    state: "failed",
    technologyPlan: null,
    investigationGraph: { nodes: [], edges: [] },
    knowledgeGraph: { claims: [], relationships: [] },
    observations: [],
    claims: [],
    goals: [],
    statistics: { nodesExecuted: 0, plannerCalls: 0, claimsCreated: 0, observationsCreated: 0, goalsSatisfied: 0, goalsTotal: 0 },
    terminationReason: "nothing to do",
  };
  const md = new ReportGenerator().render(empty);
  assert.match(md, /No claims were established/);
  assert.match(md, /No investigation nodes were created/);
});
