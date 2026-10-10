/**
 * OngoingPlanner — proposes the NEXT investigation nodes for the current goal.
 *
 * Input is the compact `BuiltContext` (progressive Tier 1/2/3 view). Output is a
 * `ValidatedBatch`: proposals that have passed schema + semantic + security +
 * budget checks. Anything that fails is dropped and reported, never executed.
 */
import type { LLMProvider } from "../llm/LLMProvider.ts";
import type { Logger } from "../util/logger.ts";
import type { BuiltContext } from "./contextTypes.ts";
import { buildOngoingPlanPrompt } from "./prompts.ts";
import { plannerNodeBatchSchema } from "./schemas.ts";
import { validateParsedBatch } from "./PlannerValidator.ts";
import type { ValidatedBatch, ValidationOptions } from "./PlannerValidator.ts";

export class OngoingPlanner {
  private readonly llm: LLMProvider;
  private readonly logger: Logger;

  constructor(llm: LLMProvider, logger: Logger) {
    this.llm = llm;
    this.logger = logger;
  }

  async plan(built: BuiltContext, opts: ValidationOptions): Promise<ValidatedBatch> {
    const request = buildOngoingPlanPrompt(built.plannerContext, built.heuristicContext);
    // Evidence categories are not action types. Constrain local runtime proposals
    // at the provider boundary as well as validating them after parsing.
    const localRuntime = built.heuristicContext.browserEnabled !== true
      && (built.heuristicContext.targets as string[] | undefined)?.includes('runtime');
    const schema = localRuntime ? {...plannerNodeBatchSchema, jsonSchema: {
      type: 'object', additionalProperties: false, required: ['nodes', 'rationale'],
      properties: {rationale: {type: 'string'}, nodes: {type: 'array', items: {
        type: 'object', additionalProperties: false, required: ['type', 'action', 'hypothesis'],
        properties: {type: {type: 'string', enum: ['read', 'execute']}, hypothesis: {type: 'string'},
          action: {anyOf: [
            {type: 'object', additionalProperties: false, required: ['type', 'filePath'],
              properties: {type: {type: 'string', enum: ['read']}, filePath: {type: 'string'}}},
            {type: 'object', additionalProperties: false, required: ['type', 'command', 'workingDirectory', 'timeoutMs'],
              properties: {type: {type: 'string', enum: ['execute']}, command: {type: 'string'},
                workingDirectory: {type: 'string'}, timeoutMs: {type: 'integer'}}},
          ]}},
      }}},
    }} : plannerNodeBatchSchema;
    const result = await this.llm.generateStructured(request, schema);
    if (!result.ok) {
      this.logger.warn("planner.ongoing.failed", { provider: result.provider, errors: result.errors, raw: result.errors.some((error) => error.startsWith("openai: HTTP ")) ? result.raw : undefined });
      return { accepted: [], rejected: [], rationale: `provider failed: ${result.errors.join("; ")}` };
    }
    const validated = validateParsedBatch(result.value, opts);
    this.logger.info("planner.ongoing.planned", {
      provider: result.provider,
      accepted: validated.accepted.length,
      rejected: validated.rejected.length,
    });
    if (validated.rejected.length) {
      this.logger.warn("planner.ongoing.rejected", {
        reasons: validated.rejected.map((r) => r.reason),
      });
    }
    return validated;
  }
}
