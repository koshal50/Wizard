import {test} from 'node:test';
import assert from 'node:assert/strict';
import {OngoingPlanner} from '../src/planner/OngoingPlanner.ts';
import {createLogger} from '../src/util/logger.ts';
import type {LLMProvider} from '../src/llm/LLMProvider.ts';
import type {BuiltContext} from '../src/planner/contextTypes.ts';

test('local runtime recovery enforces action types separately from evidence categories', async () => {
  const provider = {name: 'fixture', async generateStructured(request: any, schema: any) {
    assert.ok(schema.jsonSchema);
    const node = schema.jsonSchema.properties.nodes.items;
    assert.deepEqual(node.properties.type.enum, ['read', 'execute']);
    assert.equal(node.additionalProperties, false);
    assert.match(request.prompt, /NEVER evidence categories/);
    assert.match(request.prompt, /real startup error/);
    return {ok: true, provider: 'fixture', raw: '', value: {nodes: [{type: 'execute',
      action: {type: 'execute', command: 'node src/server.js', workingDirectory: '.', timeoutMs: 30000},
      hypothesis: 'Inspect actual runtime startup'}]}};
  }} as unknown as LLMProvider;
  const built = {heuristicContext: {targets: ['runtime'], browserEnabled: false}, plannerContext: {
    currentGoal: {name: 'Verify Runtime', technology: 'Node.js', status: 'in_progress', requirements: []},
    openQuestions: [{question: 'real startup error; missing process_execution', missingClaimType: 'RUNTIME'}],
    knowledgeGraph: {claims: []}, recentInvestigationNodes: [], repositoryContext: {readFiles: {}},
    budget: {nodeExecutionsRemaining: 10},
  }} as unknown as BuiltContext;
  const result = await new OngoingPlanner(provider, createLogger()).plan(built,
    {repoRoot: process.cwd(), budgetRemaining: 10, allowExecution: true});
  assert.equal(result.accepted.length, 1);
  assert.equal(result.rejected.length, 0);
});
