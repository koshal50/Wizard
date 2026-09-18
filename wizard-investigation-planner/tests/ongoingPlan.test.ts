/**
 * The ongoing plan's read proposals.
 *
 * The provider decides which files still need reading, and the Runtime refuses a
 * read it has already seen. The two indexes it holds answer different questions —
 * `fileObservationIds` is what has *run*, `queuedReadPaths` is what is already
 * *scheduled* — and the provider has to honour both, or it proposes work that is
 * on its way and the Runtime rejects the node as a duplicate.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { HeuristicLLMProvider } from "../src/llm/providers/HeuristicLLMProvider.ts";
import { plannerNodeBatchSchema } from "../src/planner/schemas.ts";

interface ProposedNode {
  type: string;
  action: { type: string; filePath?: string };
}

const provider = new HeuristicLLMProvider();

async function ongoingPlan(ctx: Record<string, unknown>): Promise<ProposedNode[]> {
  // The real schema, not a stub: the provider runs its output through it, so a
  // fake would test a path the planner never takes.
  const result = await provider.generateStructured(
    { purpose: "ongoing_plan", context: ctx } as never,
    plannerNodeBatchSchema as never,
  );
  assert.equal(result.ok, true, JSON.stringify((result as { errors?: unknown }).errors));
  return (result as unknown as { value: { nodes: ProposedNode[] } }).value.nodes;
}

function readPaths(nodes: ProposedNode[]): string[] {
  return nodes.filter((n) => n.type === "read").map((n) => n.action.filePath ?? "");
}

test("a priority file that has been read is not proposed again", async () => {
  const nodes = await ongoingPlan({
    priorityFiles: ["package.json"],
    fileObservationIds: { "package.json": "obs_1" },
  });
  assert.deepEqual(readPaths(nodes), []);
});

test("a priority file that has not been read is proposed", async () => {
  const nodes = await ongoingPlan({
    priorityFiles: ["package.json"],
    fileObservationIds: {},
  });
  assert.deepEqual(readPaths(nodes), ["package.json"]);
});

test("a priority file whose read is already queued is not proposed again", async () => {
  // The read has not run, so it is absent from fileObservationIds — but a node
  // for it is already in the Runtime's graph, and a second one can only produce
  // the same evidence.
  const nodes = await ongoingPlan({
    priorityFiles: ["package.json"],
    fileObservationIds: {},
    queuedReadPaths: ["package.json"],
  });
  assert.deepEqual(readPaths(nodes), []);
});

test("the queued-read comparison ignores the separator the planner holds", async () => {
  // The Runtime's queue carries whatever the validator resolved, the file list
  // carries the platform's native form. Two spellings of one file is one file.
  const nodes = await ongoingPlan({
    priorityFiles: ["client\\src\\app.js"],
    fileObservationIds: {},
    queuedReadPaths: ["client/src/app.js"],
  });
  assert.deepEqual(readPaths(nodes), []);
});

test("an unqueued file is still proposed alongside a queued one", async () => {
  const nodes = await ongoingPlan({
    priorityFiles: ["package.json", "docker-compose.yml"],
    fileObservationIds: {},
    queuedReadPaths: ["package.json"],
  });
  assert.deepEqual(readPaths(nodes), ["docker-compose.yml"]);
});

test("an absent queuedReadPaths is not an error", async () => {
  // Older Runtime, or any caller that does not send it: the plan is what it was
  // before the field existed, rather than empty.
  const nodes = await ongoingPlan({ priorityFiles: ["package.json"] });
  assert.deepEqual(readPaths(nodes), ["package.json"]);
});


// ── The interaction script ────────────────────────────────────────────────────
// Reading a page and operating it are different investigations, and only the
// first used to be reachable: the browser could navigate, snapshot and extract,
// so every WEB claim came from looking. These tests are the second half.

const LOGIN_PAGE = [
  { role: "textbox", name: "Email", selector: 'role=textbox[name="Email"]',
    tag: "input", input_type: "email", in_form: true, form_index: 0, visible: true, value: "" },
  { role: "textbox", name: "Password", selector: 'role=textbox[name="Password"]',
    tag: "input", input_type: "password", in_form: true, form_index: 0, visible: true, value: "" },
  { role: "button", name: "Sign in", selector: 'role=button[name="Sign in"]',
    tag: "button", in_form: true, form_index: 0, visible: true },
];

async function browserNodes(ctx: Record<string, unknown>): Promise<
  { nodeId?: string; action: { tool: string; selector?: string; text?: string }; dependencies?: string[]; hypothesis: string }[]
> {
  const nodes = await ongoingPlan(ctx);
  return nodes.filter((n) => n.type === "browser") as never;
}

test("a question about operating the page produces the script, chained", async () => {
  const nodes = await browserNodes({
    browserEnabled: true,
    allowedDomains: ["app.test"],
    question: "log in to the app and check the form",
    pageUrl: "https://app.test/login",
    pageControls: LOGIN_PAGE,
    // The WEB requirement is what makes the browser reachable at all, exactly as
    // it gates the navigate rule above.
    missingRequirements: [{ claimType: "WEB", description: "no WEB claims yet" }],
  });

  assert.deepEqual(nodes.map((n) => n.action.tool), ["type", "type", "click"]);
  assert.deepEqual(nodes.map((n) => n.action.selector), [
    'role=textbox[name="Email"]',
    'role=textbox[name="Password"]',
    'role=button[name="Sign in"]',
  ]);
  assert.equal(nodes[0]!.action.text, "wizard.probe@example.test");
  // Ordered, and the order is expressed in the graph rather than hoped for: a
  // form filled after it was submitted is not the same operation.
  assert.deepEqual(nodes[0]!.dependencies, []);
  assert.deepEqual(nodes[1]!.dependencies, [nodes[0]!.nodeId]);
  assert.deepEqual(nodes[2]!.dependencies, [nodes[1]!.nodeId]);
  // The step's reason is the hypothesis, so the trace shows WHY each step ran.
  assert.match(nodes[2]!.hypothesis, /submits the form/);
});

test("a question that never mentions operating the app produces no script", async () => {
  // Pressing a form's controls mutates a running application. A run that only
  // asked what a repository contains has not asked for that, and without this
  // gate every run against a URL would sign up an account somewhere.
  const nodes = await browserNodes({
    browserEnabled: true,
    allowedDomains: ["app.test"],
    question: "which dependencies does this project use",
    pageUrl: "https://app.test/login",
    pageControls: LOGIN_PAGE,
    missingRequirements: [{ claimType: "WEB", description: "no WEB claims yet" }],
  });
  assert.deepEqual(nodes.map((n) => n.action.tool), []);
});

test("no browser plane, no script — the controls are not permission", async () => {
  const nodes = await browserNodes({
    browserEnabled: false,
    allowedDomains: ["app.test"],
    question: "log in to the app",
    pageUrl: "https://app.test/login",
    pageControls: LOGIN_PAGE,
    missingRequirements: [{ claimType: "WEB", description: "no WEB claims yet" }],
  });
  assert.deepEqual(nodes.map((n) => n.action.tool), []);
});

test("a control already acted on is not proposed again", async () => {
  // Browser tools are exempt from the Runtime's duplicate dedup, so a repeat is
  // not rejected — it runs, re-types over the field, and costs a budget slot.
  const nodes = await browserNodes({
    browserEnabled: true,
    allowedDomains: ["app.test"],
    question: "log in to the app",
    pageUrl: "https://app.test/login",
    pageControls: LOGIN_PAGE,
    interactedSelectors: ['role=textbox[name="Email"]', 'role=textbox[name="Password"]'],
    missingRequirements: [{ claimType: "WEB", description: "no WEB claims yet" }],
  });
  assert.deepEqual(nodes.map((n) => n.action.tool), ["click"]);
});
