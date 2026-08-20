/**
 * EscalationEngine — the bridge between an UNEXPECTED result and the Planner.
 *
 * When the deterministic evaluator returns UNEXPECTED and the node's
 * `unexpectedAction` is "escalate_to_planner", the Runtime asks this engine to
 * build an `EscalationContext` from the node + its observation and consult the
 * EscalationPlanner. Recovery proposals come back validated and are inserted by
 * the scheduler like any other nodes.
 *
 * If `unexpectedAction` is "record_only", NO planner call is made — the surprise
 * is simply recorded. This is a key lever for minimising LLM usage.
 */
import type {
  BudgetSummary,
  EscalationContext,
  Goal,
  InvestigationNode,
  Observation,
} from "../core/types.ts";
import type { InvestigationPlanner } from "../planner/InvestigationPlanner.ts";
import type { ValidatedBatch, ValidationOptions } from "../planner/PlannerValidator.ts";
import type { Logger } from "../util/logger.ts";

export interface EscalationDeps {
  planner: InvestigationPlanner;
  logger: Logger;
}

export interface EscalationInput {
  investigationId: string;
  node: InvestigationNode;
  observation: Observation;
  currentGoal: Goal;
  budget: BudgetSummary;
  heuristicContext: Record<string, unknown>;
  validation: ValidationOptions;
}

export class EscalationEngine {
  private readonly deps: EscalationDeps;

  constructor(deps: EscalationDeps) {
    this.deps = deps;
  }

  /** Returns the validated recovery batch, or an empty batch when record-only. */
  async escalate(input: EscalationInput): Promise<ValidatedBatch> {
    const context: EscalationContext = {
      investigationId: input.investigationId,
      node: {
        nodeId: input.node.nodeId,
        type: input.node.type,
        action: describeAction(input.node),
        hypothesis: input.node.hypothesis,
        status: input.node.status,
        outcome: "UNEXPECTED",
      },
      hypothesis: input.node.hypothesis,
      observation: {
        observationId: input.observation.observationId,
        type: input.observation.type,
        summary: summarizeObservation(input.observation),
      },
      currentGoal: {
        goalId: input.currentGoal.goalId,
        name: input.currentGoal.name,
        technology: input.currentGoal.technology,
        status: input.currentGoal.status,
        requirements: input.currentGoal.requirements.map((r) => r.description),
      },
      budget: input.budget,
    };

    this.deps.logger.info("escalation.invoked", { nodeId: input.node.nodeId });
    return this.deps.planner.planEscalation(context, input.heuristicContext, input.validation);
  }
}

function describeAction(n: InvestigationNode): string {
  const a = n.action;
  switch (a.type) {
    case "read":
      return `read ${a.filePath}`;
    case "execute":
      return `exec \`${a.command}\``;
    case "parse":
      return `parse(${a.parser})`;
    case "discovery":
      return `discover "${a.pattern}"`;
    default:
      return a.type;
  }
}

function summarizeObservation(o: Observation): string {
  const d = o.data as Record<string, unknown>;
  switch (o.type) {
    case "command_result":
      return `\`${String(d.command)}\` exit=${d.exitCode === null ? "n/a" : d.exitCode} ${d.timedOut ? "(timed out)" : ""}`.trim();
    case "file_content":
      return `${String(d.filePath)} exists=${d.exists}`;
    case "parse_result":
      return `parse(${String(d.parser)}) ok=${d.ok}`;
    case "error":
      return `error: ${String(d.message)}`;
    default:
      return o.type;
  }
}
