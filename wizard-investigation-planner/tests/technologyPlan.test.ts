/**
 * Whether a plan asks the run to execute the project's tests.
 *
 * A repository with a test suite and a plan that never runs it is the failure
 * this guards: the run reads a dozen files, executes `node --version`, and can
 * say nothing about whether the project works. The signal available at plan
 * time is the file list — the test script in package.json is only discovered
 * during the run, so the goal has to be asked for on the strength of the test
 * *files*, and the probe that answers it decides the rest.
 */
import { test } from "node:test";
import assert from "node:assert/strict";
import { HeuristicLLMProvider } from "../src/llm/providers/HeuristicLLMProvider.ts";
import { technologyPlanSchema } from "../src/planner/schemas.ts";

interface Tech {
  name: string;
  initialGoals: string[];
}

const provider = new HeuristicLLMProvider();

async function techPlan(manifest: Record<string, unknown>): Promise<Tech[]> {
  // The real schema: the provider validates its own output against it, so a
  // stub here would exercise a path the planner never takes.
  const result = await provider.generateStructured(
    { purpose: "technology_plan", context: { manifest } } as never,
    technologyPlanSchema as never,
  );
  assert.equal(result.ok, true, JSON.stringify((result as { errors?: unknown }).errors));
  return (result as unknown as { value: { technologies: Tech[] } }).value.technologies;
}

const NODE_MANIFEST = {
  languages: ["JavaScript"],
  packageManagers: ["npm"],
  keyFiles: ["package.json"],
};

function goalsFor(techs: Tech[], name: string): string[] {
  const found = techs.find((t) => t.name === name);
  assert.ok(found, `no ${name} technology in ${JSON.stringify(techs.map((t) => t.name))}`);
  return found.initialGoals;
}

test("a repository with test files gets a goal that runs them", async () => {
  const techs = await techPlan({
    ...NODE_MANIFEST,
    treeFiles: ["package.json", "server/__tests__/auth.test.js", "server/index.js"],
  });
  assert.ok(goalsFor(techs, "Node.js").includes("Verify Test Suite"));
});

test("a repository with no test files is not asked to run a suite it does not have", async () => {
  // The goal would be honest about finding nothing, but it would spend a probe
  // and a slot of the budget to say so. Absent files, absent goal.
  const techs = await techPlan({
    ...NODE_MANIFEST,
    treeFiles: ["package.json", "server/index.js", "README.md"],
  });
  assert.deepEqual(goalsFor(techs, "Node.js"), ["Verify Runtime", "Verify Dependencies"]);
});

test("a missing file list is not read as a repository without tests", async () => {
  // Absent and empty are the same input here, and neither is evidence of
  // anything. The goal is simply not proposed.
  const techs = await techPlan(NODE_MANIFEST);
  assert.ok(!goalsFor(techs, "Node.js").includes("Verify Test Suite"));
});

test("the goal follows the files, not the language", async () => {
  // A Python repository with pytest files gets the same goal as a Node one.
  // The goal is routed by its own name, so the probe is chosen from whichever
  // technology carries it.
  const techs = await techPlan({
    languages: ["Python"],
    keyFiles: ["requirements.txt"],
    treeFiles: ["requirements.txt", "tests/test_api.py", "app/main.py"],
  });
  assert.ok(goalsFor(techs, "Python").includes("Verify Test Suite"));
});

test("test-file detection covers the layouts projects actually use", async () => {
  const layouts = [
    "server/__tests__/auth.test.js",
    "src/components/Button.test.tsx",
    "src/components/Button.spec.ts",
    "tests/test_api.py",
    "test/test_helper.rb",
    "pkg/handler_test.go",
    "__tests__/anything.js",
    "spec/models/user_spec.rb",
  ];
  for (const file of layouts) {
    const techs = await techPlan({ ...NODE_MANIFEST, treeFiles: ["package.json", file] });
    assert.ok(
      goalsFor(techs, "Node.js").includes("Verify Test Suite"),
      `${file} should count as a test file`,
    );
  }
});

test("a file that merely mentions test in its name is not a test suite", async () => {
  // `contest/entry.js` and `latest.js` contain the letters; neither is a suite.
  // The pattern anchors on separators so the word has to stand alone.
  for (const file of ["contest/entry.js", "latest.js", "src/latest/index.js"]) {
    const techs = await techPlan({ ...NODE_MANIFEST, treeFiles: ["package.json", file] });
    assert.ok(
      !goalsFor(techs, "Node.js").includes("Verify Test Suite"),
      `${file} should not count as a test file`,
    );
  }
});

test("a Windows-style path is detected the same as a POSIX one", async () => {
  // treeFiles carries the platform's separator; the pattern has to accept both
  // or the goal silently disappears on Windows.
  const techs = await techPlan({
    ...NODE_MANIFEST,
    treeFiles: ["package.json", "server\\__tests__\\auth.test.js"],
  });
  assert.ok(goalsFor(techs, "Node.js").includes("Verify Test Suite"));
});
