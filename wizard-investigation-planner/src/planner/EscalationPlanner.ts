/**
 * EscalationPlanner — invoked ONLY when a node produces an UNEXPECTED result
 * (the deterministic evaluator could not classify it as SUCCESS or FAILURE).
 *
 * This is the single sanctioned place an LLM is consulted mid-investigation.
 * Keeping escalation separate from the ongoing planner is what lets the Runtime
 * minimise LLM calls: the common path is fully deterministic, and only genuine
 * surprises pay for a model call.
 *
 * Output is validated exactly like the ongoing planner's, so escalation recovery
 * nodes are just as safe as any other.
 */
import type { EscalationContext } from "../core/types.ts";
import type { LLMProvider } from "../llm/LLMProvider.ts";
import type { Logger } from "../util/logger.ts";
import { buildEscalationPrompt } from "./prompts.ts";
import { plannerNodeBatchSchema } from "./schemas.ts";
import { validateParsedBatch } from "./PlannerValidator.ts";
import type { ValidatedBatch, ValidationOptions } from "./PlannerValidator.ts";

export class EscalationPlanner {
  private readonly llm: LLMProvider;
  private readonly logger: Logger;

  constructor(llm: LLMProvider, logger: Logger) {
    this.llm = llm;
    this.logger = logger;
  }

  async plan(
    escalation: EscalationContext,
    heuristicContext: Record<string, unknown>,
    opts: ValidationOptions,
  ): Promise<ValidatedBatch> {
    const request = buildEscalationPrompt(escalation, heuristicContext);
    const result = await this.llm.generateStructured(request, plannerNodeBatchSchema);
    if (!result.ok) {
      this.logger.warn("planner.escalation.failed", { provider: result.provider, errors: result.errors });
      return { accepted: [], rejected: [], rationale: `provider failed: ${result.errors.join("; ")}` };
    }
    const validated = validateParsedBatch(result.value, opts);
    this.logger.info("planner.escalation.planned", {
      provider: result.provider,
      accepted: validated.accepted.length,
      rejected: validated.rejected.length,
    });
    return validated;
  }
}
