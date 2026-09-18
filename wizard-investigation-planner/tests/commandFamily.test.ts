/**
 * Whether `wizard investigate`, `verify`, `report` and `explain` are four
 * commands or one.
 *
 * They were one. Every family inherited the manifest's whole goal set
 * unconditionally and could only add to it, so `report` ran the test suite,
 * `explain architecture` ran the runtime probe, and four runs against one
 * repository differed by at most one goal name. The family had a single lever in
 * the system — the Runtime reads `inv.intent` only to hand it to the Planner —
 * and nothing was pulling it.
 *
 * These tests are about the lever, and about the two ways it can be wrong. A
 * family that removes too little is the bug above. A family that removes too
 * much produces a run that does nothing and reports honestly on having done
 * nothing, which is indistinguishable from a repository with nothing in it.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { HeuristicLLMProvider } from "../src/llm/providers/HeuristicLLMProvider.ts";
import { technologyPlanSchema } from "../src/planner/schemas.ts";
import {
  goalEvidenceFor,
  goalsNamedBy,
  goalsNamedByRequest,
  type CommandFamily,
} from "../src/planner/goalPolicy.ts";
import { goalDefFor } from "../src/http/contracts.ts";

interface Tech {
  name: string;
  initialGoals: string[];
  priorityFiles: string[];
  signals: string[];
}

const provider = new HeuristicLLMProvider();

/** A Node repository with a suite, a Dockerfile, and an auth module. */
const MANIFEST = {
  languages: ["JavaScript"],
  packageManagers: ["npm"],
  keyFiles: ["package.json", "Dockerfile"],
  treeFiles: [
    "package.json",
    "Dockerfile",
    "server/index.js",
    "server/routes/auth.js",
    "server/middleware/auth.js",
    "server/__tests__/auth.test.js",
  ],
};

/** Plan with the default manifest, or with a `treeFiles` of its own when a test
 * is about what the repository has rather than about the command family. */
async function plan(
  intent: string,
  targets: string[] = [],
  question = "",
  treeFiles?: string[],
): Promise<Tech[]> {
  const manifest = treeFiles ? { ...MANIFEST, treeFiles } : MANIFEST;
  const result = await provider.generateStructured(
    {
      purpose: "technology_plan",
      context: { manifest: { ...manifest, intent, targets, question } },
    } as never,
    technologyPlanSchema as never,
  );
  assert.equal(result.ok, true, JSON.stringify((result as { errors?: unknown }).errors));
  return (result as unknown as { value: { technologies: Tech[] } }).value.technologies;
}

/** Every goal on the plan, flattened, because which technology carries one is
 * not what any of these tests are about. */
function goals(techs: Tech[]): string[] {
  return techs.flatMap((t) => t.initialGoals);
}

function files(techs: Tech[]): string[] {
  return techs.flatMap((t) => t.priorityFiles);
}

// ── The four families are four commands ──────────────────────────────────────

test("four families produce four different plans for one repository", async () => {
  const runs = await Promise.all([
    plan("investigate", ["architecture"]),
    plan("verify", ["runtime"]),
    plan("report"),
    plan("explain", ["architecture"]),
  ]);
  const sets = runs.map((t) => goals(t).slice().sort().join("|"));
  assert.equal(new Set(sets).size, 4, `families collided:\n${sets.join("\n")}`);
});

test("report runs nothing at all", async () => {
  // "A report is not a proof." Every goal a report keeps has to be one a file
  // can close, or the command quietly becomes an investigation.
  const techs = await plan("report");
  const proven = goals(techs).filter((g) => goalEvidenceFor(g).requires_execution_evidence);
  assert.deepEqual(proven, [], `report kept execution goals: ${proven.join(", ")}`);
});

test("report does not go looking for a question it was never asked", async () => {
  // `report` takes no target, so an `Inspect …` goal cannot be an answer to
  // anything — it would only be the manifest's files read under a name nobody
  // asked for, and it would close on the same FILE_READ claim the reads that
  // were happening anyway produce.
  const techs = await plan("report");
  assert.deepEqual(goals(techs).filter((g) => /^inspect/i.test(g)), []);
});

test("explain answers the target and drops the repository-wide context", async () => {
  const techs = await plan("explain", ["architecture"]);
  assert.deepEqual(goals(techs), ["Inspect architecture"]);
});

test("explain of a goal the vocabulary knows keeps that goal and nothing else", async () => {
  // "explain the runtime" is a question about the runtime. Answering it means
  // finding out what the runtime is, which is running it — but it is not a
  // request to also establish the dependencies.
  const techs = await plan("explain", ["runtime"]);
  assert.deepEqual(goals(techs), ["Verify Runtime"]);
});

test("explain of a target nothing answers to falls back to what can be described", async () => {
  // An explanation with nothing to explain would report on an empty run and
  // look exactly like a repository with nothing in it.
  const techs = await plan("explain", ["security"]);
  assert.ok(goals(techs).length > 0, "explain produced an empty plan");
  assert.ok(goals(techs).includes("Inspect security"));
  assert.deepEqual(goals(techs).filter((g) => goalEvidenceFor(g).requires_execution_evidence), []);
});

test("investigate keeps the context the manifest suggests", async () => {
  // Understanding a repository means knowing what it is, which is what the
  // manifest's own goals are for. This is what separates investigate from
  // explain.
  const techs = await plan("investigate", ["architecture"]);
  assert.ok(goals(techs).includes("Verify Dependencies"));
  assert.ok(goals(techs).includes("Inspect architecture"));
});

test("investigate does not run what the target did not name", async () => {
  // "architecture" is a subject, not a probe. Investigating it is reading.
  const techs = await plan("investigate", ["architecture"]);
  assert.deepEqual(goals(techs).filter((g) => goalEvidenceFor(g).requires_execution_evidence), []);
});

test("investigate runs what the target did name", async () => {
  const techs = await plan("investigate", ["runtime"]);
  assert.ok(goals(techs).includes("Verify Runtime"));
});

// ── verify is the narrow one ─────────────────────────────────────────────────

test("verify is scoped to the one thing it was aimed at", async () => {
  // `verify containers` has no business running the test suite. This is the
  // difference between verify and investigate in one assertion.
  const techs = await plan("verify", ["containers"]);
  assert.deepEqual(goals(techs), ["Verify Containerization"]);
});

test("verify aimed at something the vocabulary cannot prove proves what it can", async () => {
  // "ci" is a real target and not a goal name. Reading it as "prove nothing"
  // would make the command silently do nothing, which is worse than doing the
  // widest thing it knows how to do.
  const techs = await plan("verify", ["ci"]);
  assert.ok(goals(techs).includes("Verify Test Suite"));
  for (const goal of goals(techs)) {
    assert.ok(
      goalEvidenceFor(goal).requires_execution_evidence,
      `${goal} is not something verify can prove`,
    );
  }
});

test("verify with no target proves everything provable", async () => {
  const techs = await plan("verify");
  assert.ok(goals(techs).includes("Verify Runtime"));
  assert.ok(goals(techs).includes("Verify Test Suite"));
});

// ── The family is a verb, never a subject ────────────────────────────────────

test("a command family is never read as something to go and read", async () => {
  // The bug this replaces: `intent` holds "investigate" | "verify" | "explain" |
  // "report", and matching it as text made subjects out of verbs — goals called
  // "Inspect explain" and "Inspect report" that no repository can answer, and
  // which the run then spent budget failing to close.
  for (const family of ["investigate", "verify", "explain", "report"] as CommandFamily[]) {
    for (const target of ["architecture", "runtime", "security"]) {
      const techs = await plan(family, [target]);
      for (const goal of goals(techs)) {
        assert.ok(
          !new RegExp(`^inspect (${family})$`, "i").test(goal),
          `${family} + ${target} produced "${goal}"`,
        );
      }
    }
  }
});

test("a named target is still a subject when it is not a goal", async () => {
  const techs = await plan("investigate", ["authentication"]);
  assert.ok(
    goals(techs).some((g) => /^inspect authentication$/i.test(g)),
    `no subject goal in ${goals(techs).join(", ")}`,
  );
});

// ── The user's own sentence ──────────────────────────────────────────────────

test("a question resolves to the files it names and leads the reads", async () => {
  // The sentence never reached the Planner before this: the CLI parsed it for
  // targets and dropped it, so `intentSubjects` — the code written for exactly
  // this — had never once been handed a sentence.
  const techs = await plan("investigate", [], "investigate the auth flow");
  assert.ok(
    goals(techs).some((g) => /^inspect auth flow$/i.test(g)),
    `no goal from the question in ${goals(techs).join(", ")}`,
  );
  const first = files(techs).slice(0, 2);
  for (const f of first) {
    assert.ok(/auth/i.test(f), `the question's files do not lead the reads: ${files(techs).join(", ")}`);
  }
});

test("a question that resolves to no file still leaves a trace", async () => {
  // Silently discarding a question nothing answers to is how a run reports on
  // something nobody asked about.
  const techs = await plan("investigate", [], "how does the payment flow work");
  const signals = techs.flatMap((t) => t.signals);
  assert.ok(
    signals.some((s) => s.includes("payment flow")),
    `the question left no trace: ${signals.join(" | ")}`,
  );
});

// ── The two readers of the goal vocabulary ───────────────────────────────────

test("the plan and the goal engine agree about what each goal needs", async () => {
  // The provider decides which goals a family keeps by asking whether a goal
  // needs execution; the wire edge decides what the kernel's goal engine counts
  // toward it. Two answers to one question, and a disagreement is silent: a
  // goal the plan thinks a file closes and the engine thinks needs execution
  // can never be satisfied by anything, and it reads exactly like a goal the
  // run failed to prove. This is the guard, exercised over every goal name a
  // plan can contain.
  const techs = await Promise.all([
    plan("investigate", ["architecture"]),
    plan("investigate", ["runtime"]),
    plan("verify", ["ci"]),
    plan("report"),
    plan("explain", ["authentication"]),
    plan("investigate", [], "investigate the auth flow and the test suite"),
  ]);
  const names = new Set(techs.flat().flatMap((t) => t.initialGoals));
  assert.ok(names.size >= 4, `too few goals to be a guard: ${[...names].join(", ")}`);

  for (const name of names) {
    const wire = goalDefFor(name);
    const evidence = goalEvidenceFor(name);
    assert.deepEqual(
      wire.required_claim_types,
      evidence.required_claim_types,
      `${name}: the plan and the goal engine disagree about its claim types`,
    );
    assert.equal(
      wire.requires_execution_evidence,
      evidence.requires_execution_evidence,
      `${name}: the plan and the goal engine disagree about whether it must run`,
    );
  }
});

// ── What an unstated family means ────────────────────────────────────────────

test("a family nobody stated restricts nothing", async () => {
  // Restricting is the exception, so it is the thing that has to be asked for.
  // A caller that omits the family gets the manifest's whole proposal rather
  // than an empty plan it would have no way to recognise as its own mistake.
  const techs = await plan("");
  assert.ok(goals(techs).includes("Verify Runtime"));
  assert.ok(goals(techs).includes("Verify Test Suite"));
});

test("a family the Runtime does not know restricts nothing either", async () => {
  const techs = await plan("summarise", ["architecture"]);
  assert.ok(goals(techs).includes("Verify Runtime"));
});

// ── The vocabulary itself ────────────────────────────────────────────────────

test("a target names goals through the vocabulary, not through a substring", async () => {
  // `latest` contains `test`; `contest` contains `test`. Neither is a request to
  // run a suite. The patterns anchor on word boundaries for exactly this.
  assert.deepEqual([...goalsNamedBy(["latest"])], []);
  assert.deepEqual([...goalsNamedBy(["contest"])], []);
  assert.deepEqual([...goalsNamedBy(["ci"])].sort(), ["Verify Test Suite"]);
  assert.deepEqual([...goalsNamedBy(["containers"])], ["Verify Containerization"]);
});

test("a question names goals through the vocabulary, not only a target", async () => {
  // The vocabulary exists to recognise what the user said they wanted checked,
  // and a sentence says it as plainly as a target word does. Matched against
  // targets alone, "how do the tests run" named nothing — so `investigate`
  // dropped the suite goal for having been asked for in the wrong vocabulary,
  // and the run never ran the tests it had just been asked about.
  const techs = await plan("investigate", [], "how do the tests run");
  assert.ok(
    goals(techs).includes("Verify Test Suite"),
    `the question named no goal: ${goals(techs).join(", ")}`,
  );
  const suite = goals(techs).find((g) => g === "Verify Test Suite")!;
  assert.equal(goalEvidenceFor(suite).requires_execution_evidence, true);
});

test("a question names goals only when the family would keep them", async () => {
  // `report` reads knowledge that already exists, so the same sentence names
  // the same goal and the family still refuses it. The vocabulary decides what
  // a sentence names; the family decides what the run does about it.
  const techs = await plan("report", [], "how do the tests run");
  assert.deepEqual(
    goals(techs).filter((g) => goalEvidenceFor(g).requires_execution_evidence),
    [],
    `report ran a suite on a question: ${goals(techs).join(", ")}`,
  );
});

test("a question's words become goals only where the repository answers", async () => {
  const techs = await plan("investigate", [], "why does the auth flow differ from the docker build");
  const named = goals(techs);
  assert.ok(named.includes("Inspect auth"), `no goal for "auth": ${named.join(", ")}`);
  assert.ok(named.includes("Inspect docker"), `no goal for "docker": ${named.join(", ")}`);
  // Every goal here carries real paths — the standard the rest of the plan is
  // held to. A word that matched nothing is dropped rather than turned into a
  // goal, because most of a sentence is not nouns and the run would otherwise
  // spend its budget on "Inspect differ" and "Inspect flow".
  assert.ok(!named.includes("Inspect differ"), `a word no file answers became a goal: ${named.join(", ")}`);
  assert.ok(!named.includes("Inspect does"), `a function word became a goal: ${named.join(", ")}`);
});

test("a subject the repository already covers is not a second goal", async () => {
  // "middleware" resolves to server/middleware/auth.js, and "auth" — the wider
  // word beside it in the same sentence — already reads that file. Two goals
  // over the same evidence is one goal and one wasted budget slot, so the
  // narrower word goes. The wide one stays because it is the one the user is
  // more likely to recognise in the report.
  const techs = await plan("investigate", [], "why does the auth middleware run twice");
  const named = goals(techs);
  assert.ok(named.includes("Inspect auth"), `the wider word did not survive: ${named.join(", ")}`);
  assert.ok(!named.includes("Inspect middleware"), `a covered subject became its own goal: ${named.join(", ")}`);
});

test("a question is never repeated back as a goal name", async () => {
  // The tempting shortcut — hand the whole sentence to the resolver, which
  // already tries each of its words — produces a goal called "Inspect why does
  // the auth middleware run twice". The goals are named after the words that
  // landed, so the report can answer in the user's own terms without a sentence
  // standing where a subject belongs.
  const asked = "why does the auth middleware run twice";
  const techs = await plan("investigate", [], asked);
  for (const g of goals(techs)) {
    assert.ok(!g.toLowerCase().includes(asked.slice(0, 20)), `the sentence became a goal: ${g}`);
  }
});

test("the whole request names goals, sentence included", () => {
  // The unit underneath the two tests above: one implementation, so the
  // provider that attaches a named goal and the family filter that keeps it
  // cannot disagree about which words named it.
  assert.deepEqual([...goalsNamedByRequest([], "how do the tests run")], ["Verify Test Suite"]);
  assert.deepEqual([...goalsNamedByRequest(["docker"], "")], ["Verify Containerization"]);
  assert.deepEqual(
    [...goalsNamedByRequest(["docker"], "are the tests green")].sort(),
    ["Verify Containerization", "Verify Test Suite"],
  );
  // An empty question contributes nothing, with or without targets.
  assert.deepEqual([...goalsNamedByRequest([], "")], []);
  assert.deepEqual([...goalsNamedByRequest([], "   ")], []);
});

// ── An imperative sentence is not a list of subjects ─────────────────────────

test("the clauses of an instruction do not become Inspect goals", async () => {
  // Found live. The request "log in to the app, fill the sign-up form and
  // submit it" planned three goals — "Inspect log in to the app", "Inspect fill
  // the sign-up form", "Inspect submit it". The subject extractor splits a
  // sentence on commas and "and", and none of these clauses contains an
  // interrogative, so each passed as a subject.
  //
  // They were not merely useless. Nothing in the repository answers to any of
  // them, so each required only FILE_READ, and the run's own five file reads
  // closed all three: the report showed three questions answered at 100% on
  // evidence about package.json. Those are the three lines the user reads first.
  const techs = await plan("investigate", [], "log in to the app, fill the sign-up form and submit it");
  const invented = goals(techs).filter((g) => /^Inspect\b/.test(g));
  assert.deepEqual(invented, [], `the sentence produced subject goals: ${invented}`);
});

test("a phrase out of a sentence still becomes a goal when the repository has it", async () => {
  // The rule is "resolves or is dropped", not "ignore the sentence". A clause
  // the tree answers to is a real interest and keeps its goal — otherwise this
  // fix would trade three junk goals for one missing one.
  const techs = await plan("investigate", [], "investigate the auth flow and the middleware");
  const invented = goals(techs).filter((g) => /^Inspect\b/.test(g));
  assert.ok(invented.length > 0, "a resolvable subject produced no goal");
  assert.ok(invented.every((g) => !/\band\b/i.test(g)), `clauses leaked: ${invented}`);
});

test("a target that resolves to nothing is still reported", async () => {
  // The standard that did NOT change. "architecture" is a real thing to ask
  // about and is not a filename; dropping it would leave the run reporting on a
  // question nobody asked while the one that was asked left no trace.
  const techs = await plan("investigate", ["architecture"]);
  assert.ok(goals(techs).includes("Inspect architecture"), goals(techs).join(", "));
});

test("one generic word out of a clause does not make the clause a name", async () => {
  // The half of the same bug that dropping unresolvable clauses did not fix.
  // "fill the sign-up form" does not resolve to nothing — the word "form" is in
  // TaskForm.jsx — so it survived as "Inspect fill the sign-up form", 100%
  // satisfied by whichever file the run read next. The repository answering to
  // one ordinary word inside a clause is not the repository answering to the
  // clause, and a goal named after an instruction is still not a question.
  //
  // What survives is the single word, by a different and deliberate route:
  // `questionWords` keeps a word the tree contains, which is how the run knew
  // to read TaskForm.jsx at all. A word the user typed is a weaker interest
  // than a name they gave, but it is not an invention, and this asserts the
  // line between the two rather than a ban on deriving anything from prose.
  const tree = [
    "client/src/components/TaskForm.jsx",
    "client/src/components/TaskList.jsx",
    "package.json",
  ];
  const techs = await plan(
    "investigate",
    [],
    "log in to the app, fill the sign-up form and submit it",
    tree,
  );
  const clauses = goals(techs).filter(
    (g) => /^Inspect\b/.test(g) && g.replace(/^Inspect\s+/, "").split(/\s+/).length > 1,
  );
  assert.deepEqual(clauses, [], `a clause resolved through one of its words: ${clauses}`);
});

test("a target may still land on a shorter version of itself", async () => {
  // The standard that did NOT change, on the other side of the same line. A
  // target is a name the user chose, so its own word is a shorter version of
  // that name: someone asking about "authentication" in a repository with
  // auth.js means auth.js. Only phrases lifted out of prose are held to
  // resolving whole, because only they were never names to begin with.
  const tree = ["server/routes/auth.js", "server/src/server.js"];
  const techs = await plan("investigate", ["authentication"], "", tree);
  assert.ok(goals(techs).includes("Inspect authentication"), goals(techs).join(", "));
});
