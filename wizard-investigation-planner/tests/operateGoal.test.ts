/**
 * Operating the app is a goal, and a goal is only worth declaring if the run can
 * close it.
 *
 * This file exists because of a live failure with no test behind it. A run was
 * asked to "log in to the app, fill the sign-up form and submit it" against a
 * real dev server. It navigated to the page, satisfied every goal the plan had
 * declared, and finished after six nodes — with the form untouched. Nothing in
 * the suite failed, because nothing in the suite ever asked whether the plan's
 * goals and the provider's rules were talking about the same thing.
 *
 * So the assertions here are about an AGREEMENT, not about either half alone:
 *
 *   - planner/goalPolicy.ts decides what "operate the web surface" is proven by;
 *   - http/contracts.ts declares the goal from that decision;
 *   - the provider writes the steps from the same gate.
 *
 * A plan that declares the goal with no steps to satisfy it, and a script with
 * no goal to justify it, are both failures — the first burns the budget and
 * reports the request unanswered, the second mutates someone's page for a run
 * that never claimed it would.
 */
import { strict as assert } from "node:assert";
import { test } from "node:test";

import {
  ACTS_ON_PAGE,
  goalEvidenceFor,
  NAMED_GOALS,
  operatesSurface,
} from "../src/planner/goalPolicy.ts";
import { technologyPlanToWire, type WireTechnologyPlan } from "../src/http/contracts.ts";
import { HeuristicLLMProvider } from "../src/llm/providers/HeuristicLLMProvider.ts";
import { plannerNodeBatchSchema } from "../src/planner/schemas.ts";
import type { PageControl } from "../src/planner/interactionScript.ts";
import type { TechnologyPlan } from "../src/core/types.ts";

const URL = "http://localhost:5173/register";

// The page the Runtime's controls observation produces for a sign-up route, in
// the kernel's own snake_case — copied in shape from tests/ongoingPlan.test.ts,
// because a fixture that drifts from the wire would test a page nobody sends.
const LOGIN_PAGE: PageControl[] = [
  { role: "textbox", name: "Email", selector: 'role=textbox[name="Email"]',
    tag: "input", input_type: "email", in_form: true, form_index: 0,
    visible: true, value: "" },
  { role: "textbox", name: "Password", selector: 'role=textbox[name="Password"]',
    tag: "input", input_type: "password", in_form: true, form_index: 0,
    visible: true, value: "" },
  { role: "button", name: "Create account", selector: 'role=button[name="Create account"]',
    tag: "button", in_form: true, form_index: 0, visible: true },
];

const provider = new HeuristicLLMProvider();

/** A plan with no Web technology — what the manifest alone produces for a URL target. */
function planWithoutWeb(): TechnologyPlan {
  return {
    technologies: [{
      name: "TypeScript", confidence: "high", signals: ["package.json"],
      initialGoals: ["Verify Dependencies"], priorityFiles: [],
    }],
  };
}

function goalsOf(plan: WireTechnologyPlan): string[] {
  return plan.technologies.flatMap((t) => t.initial_goals.map((g) => g.name));
}

function webGoal(plan: WireTechnologyPlan, name: string) {
  for (const t of plan.technologies) {
    const hit = t.initial_goals.find((g) => g.name === name);
    if (hit) return hit;
  }
  return undefined;
}

async function scriptFor(question: string, browserEnabled = true) {
  const result = await provider.generateStructured(
    {
      purpose: "ongoing_plan",
      context: {
        browserEnabled,
        allowedDomains: ["localhost"],
        browserTargets: [URL],
        pageUrl: URL,
        pageControls: LOGIN_PAGE,
        interactedSelectors: [],
        question,
        targets: [URL],
      },
    } as never,
    plannerNodeBatchSchema as never,
  );
  assert.equal(result.ok, true, JSON.stringify((result as { errors?: unknown }).errors));
  const nodes = (result as unknown as {
    value: { nodes: Array<{ type: string; action: { tool?: string } }> };
  }).value.nodes;
  return nodes.filter((n) => n.type === "browser").map((n) => n.action.tool ?? "");
}

// ── The gate ────────────────────────────────────────────────────────────────

test("a request that asks for an action names an operation", () => {
  assert.ok(operatesSurface("log in to the app, fill the sign-up form and submit it", [URL]));
  assert.ok(operatesSurface("sign up", []));
  assert.ok(operatesSurface("drive the app", []));
  assert.ok(operatesSurface("check the frontend", []));
  assert.ok(operatesSurface("click through the checkout", [URL]));
  // A sentence in the target position is still a sentence.
  assert.ok(operatesSurface("", ["log in and submit the form"]));
});

test("a request that asks a question does not", () => {
  // The false positive that narrowed this regex: "use" was in it, so asking
  // which dependencies a project uses read as an instruction to type into a
  // login form. A false negative costs a step; a false positive mutates a page.
  assert.ok(!operatesSurface("which dependencies does this project use", []));
  assert.ok(!operatesSurface("how does this get deployed", []));
  assert.ok(!operatesSurface("verify the test suite is real", []));
  assert.ok(!operatesSurface("explain the architecture", []));
  assert.ok(!operatesSurface("", []));
});

test("an address is a location, not an instruction", () => {
  // The second false positive, and the one that survives any word list that
  // contains "register": the app's own route name is in the target, so a gate
  // reading targets as words sends a run to submit a form because it was
  // pointed at /register. Killing the words would not fix this — only ignoring
  // the address does.
  assert.ok(!operatesSurface("which routes does this client define", [URL]));
  assert.ok(!operatesSurface("", ["http://localhost:5173/register"]));
  assert.ok(!operatesSurface("", ["https://app.example.test/sign-up"]));
  // A non-address target keeps its words: `verify "click the checkout"` is an
  // instruction however it was typed.
  assert.ok(operatesSurface("", ["click the checkout"]));
  // And the sentence still counts when an address is present.
  assert.ok(operatesSurface("log in and submit", [URL]));
});

test("the goal-name matcher and the operation gate share one word list", () => {
  // Two copies would drift, and the drift is silent: a goal named by one and
  // scripted by the other, or the reverse.
  const named = NAMED_GOALS.find((g) => g.name === "Operate Web Surface");
  assert.ok(named, "no goal is named by the operation words");
  assert.equal(named.namedBy, ACTS_ON_PAGE);
});

// ── What the goal is proven by ──────────────────────────────────────────────

test("operating the web surface is proven by INTERACTION, not by reaching a page", () => {
  const evidence = goalEvidenceFor("Operate Web Surface");
  assert.deepEqual(evidence.required_claim_types, ["INTERACTION"]);
  assert.equal(evidence.requires_execution_evidence, true);
});

test("the operate route wins over the web route it contains", () => {
  // "Operate Web Surface" contains "Web". Only the prefix test keeps it from
  // being routed as the read-the-page goal it is the opposite of — and a WEB
  // goal is closed by the navigate that caused the bug.
  assert.deepEqual(goalEvidenceFor("Verify Web Surface").required_claim_types, ["WEB"]);
  assert.notDeepEqual(
    goalEvidenceFor("Operate Web Surface").required_claim_types,
    goalEvidenceFor("Verify Web Surface").required_claim_types,
  );
});

// ── The declaration ─────────────────────────────────────────────────────────

test("the goal is declared only when the request asked for it", () => {
  const quiet = technologyPlanToWire(planWithoutWeb(), [URL], false);
  assert.ok(goalsOf(quiet).includes("Verify Web Surface"));
  assert.ok(!goalsOf(quiet).includes("Operate Web Surface"));

  const loud = technologyPlanToWire(planWithoutWeb(), [URL], true);
  assert.ok(goalsOf(loud).includes("Verify Web Surface"));
  assert.ok(goalsOf(loud).includes("Operate Web Surface"));
});

test("no browser plane means no browser goal at all", () => {
  const plan = technologyPlanToWire(planWithoutWeb(), [], true);
  assert.ok(!goalsOf(plan).some((n) => /web surface/i.test(n)));
});

test("a goal the plan already carries is not declared twice", () => {
  // The provider attaches a requested goal to the plan's primary technology
  // before this edge runs. Pushing unconditionally would declare one goal twice
  // — two goals one piece of evidence closes, and a report that says a thing was
  // proved twice.
  const plan: TechnologyPlan = {
    technologies: [{
      name: "Web", confidence: "high", signals: [],
      initialGoals: ["Verify Web Surface", "Operate Web Surface"], priorityFiles: [],
    }],
  };
  const wired = technologyPlanToWire(plan, [URL], true);
  const names = goalsOf(wired);
  assert.equal(names.filter((n) => n === "Operate Web Surface").length, 1);
  assert.equal(names.filter((n) => n === "Verify Web Surface").length, 1);
});

test("the declared goal carries the evidence routing, not a default", () => {
  const wired = technologyPlanToWire(planWithoutWeb(), [URL], true);
  const op = webGoal(wired, "Operate Web Surface");
  assert.ok(op, "operate goal missing");
  assert.deepEqual(op.required_claim_types, ["INTERACTION"]);
  assert.equal(op.requires_execution_evidence, true);
});

// ── The agreement between the two halves ────────────────────────────────────

test("a run asked to operate the app is given steps to operate it with", async () => {
  const tools = await scriptFor("log in to the app, fill the sign-up form and submit it");
  assert.deepEqual(tools, ["type", "type", "click"]);

  const declared = goalsOf(technologyPlanToWire(planWithoutWeb(), [URL], true));
  assert.ok(declared.includes("Operate Web Surface"));
});

test("a run not asked to operate the app gets neither the goal nor the steps", async () => {
  const question = "which routes does this client define";
  assert.ok(!operatesSurface(question, [URL]));
  assert.deepEqual(await scriptFor(question), []);

  const declared = goalsOf(technologyPlanToWire(planWithoutWeb(), [URL], false));
  assert.ok(!declared.includes("Operate Web Surface"));
  // Reaching the page is still worth doing, so the read-the-page goal remains.
  assert.ok(declared.includes("Verify Web Surface"));
});

test("no browser plane means no steps, whatever the question asks for", async () => {
  assert.deepEqual(await scriptFor("log in and submit the form", false), []);
});
