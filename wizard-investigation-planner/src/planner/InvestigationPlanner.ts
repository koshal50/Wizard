/**
 * InvestigationPlanner — the facade the Runtime talks to.
 *
 * It composes the three specialised planners (technology / ongoing / escalation)
 * and exposes exactly what the Runtime needs. It embodies the core contract:
 *
 *   "The Planner ONLY creates structured investigation requests. It never reads
 *    files, executes commands, modifies graphs, creates claims, marks goals
 *    complete, or sets trust."
 *
 * Everything this class returns is a *proposal* (validated but not materialised).
 * The Runtime decides whether/when to turn proposals into real nodes.
 */
import type {
  EscalationContext,
  TechnologyPlan,
} from "../core/types.ts";
import type { RepositoryManifest } from "../manifest/types.ts";
import type { LLMProvider } from "../llm/LLMProvider.ts";
import type { Logger } from "../util/logger.ts";
import { TechnologyPlanner } from "./TechnologyPlanner.ts";
import { OngoingPlanner } from "./OngoingPlanner.ts";
import { EscalationPlanner } from "./EscalationPlanner.ts";
import type { BuiltContext } from "./contextTypes.ts";
import type { ValidatedBatch, ValidationOptions } from "./PlannerValidator.ts";

export class InvestigationPlanner {
  private readonly technology: TechnologyPlanner;
  private readonly ongoing: OngoingPlanner;
  private readonly escalation: EscalationPlanner;

  constructor(llm: LLMProvider, logger: Logger) {
    this.technology = new TechnologyPlanner(llm, logger);
    this.ongoing = new OngoingPlanner(llm, logger);
    this.escalation = new EscalationPlanner(llm, logger);
  }

  planTechnologies(manifest: RepositoryManifest): Promise<TechnologyPlan> {
    return this.technology.plan(manifest);
  }

  planNext(built: BuiltContext, opts: ValidationOptions): Promise<ValidatedBatch> {
    return this.ongoing.plan(built, opts);
  }

  planEscalation(
    escalation: EscalationContext,
    heuristicContext: Record<string, unknown>,
    opts: ValidationOptions,
  ): Promise<ValidatedBatch> {
    return this.escalation.plan(escalation, heuristicContext, opts);
  }
}
