import { test } from 'node:test';
import assert from 'node:assert/strict';
import { TechnologyPlanner } from '../src/planner/TechnologyPlanner.ts';
import { manifestFromWire } from '../src/http/contracts.ts';
import { createLogger } from '../src/util/logger.ts';
import type { LLMProvider } from '../src/llm/LLMProvider.ts';

const provider = {
  name: 'fixture',
  async generateStructured() {
    return {ok: true, provider: 'fixture', raw: '', value: {technologies: [
      {name: 'Python', confidence: 'high', signals: ['main.py'], initialGoals: ['Verify Runtime'], priorityFiles: ['src/main.py']},
      {name: 'Other', confidence: 'medium', signals: [], initialGoals: ['Unrequested execution'], priorityFiles: []},
    ]}};
  },
} as unknown as LLMProvider;

const manifest = manifestFromWire({root_path: '.', directory_tree: ['src/main.py', 'src/deep/app.py', 'tests/main.py']} as never);
test('local architecture scope cannot acquire execution goals from model output', async () => {
  const plan = await new TechnologyPlanner(provider, createLogger()).plan(manifest, 'investigate', ['architecture']);
  assert.deepEqual(plan.technologies.flatMap(t => t.initialGoals), ['Inspect Architecture']);
  assert.deepEqual(plan.technologies[0]?.priorityFiles, ['src/main.py']);
});
test('runtime verification goal policy is preserved', async () => {
  const plan = await new TechnologyPlanner(provider, createLogger()).plan(manifest, 'verify', ['runtime']);
  assert.equal(plan.technologies[0]?.initialGoals[0], 'Verify Runtime');
});
test('source entry candidates are actual discovered paths, excluding tests', () => {
  assert.deepEqual(manifest.entryFiles, ['src/main.py', 'src/deep/app.py']);
});

test('explain dependencies cannot acquire runtime or browser verification goals', async () => {
  const plan = await new TechnologyPlanner(provider, createLogger()).plan(manifest, 'explain', ['dependencies']);
  assert.deepEqual(plan.technologies.flatMap(t => t.initialGoals), ['Inspect Dependencies']);
});

test('explain seed paths normalize manifest and model slash styles before deduplication', async () => {
  const fixture = {name: 'fixture', async generateStructured() {
    return {ok:true, provider:'fixture', raw:'', value:{technologies:[{name:'Node',confidence:'high',signals:[],
      initialGoals:['Verify Web Surface'],priorityFiles:['server/package.json']}]}};
  }} as unknown as LLMProvider;
  const mixed = {...manifest, keyFiles:[{path:'server\\package.json',sizeBytes:0,extension:'.json'}]};
  const plan = await new TechnologyPlanner(fixture, createLogger()).plan(mixed, 'explain', ['dependencies']);
  assert.deepEqual(plan.technologies[0]?.priorityFiles, ['server/package.json']);
});
