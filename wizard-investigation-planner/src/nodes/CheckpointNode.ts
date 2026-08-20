/**
 * Checkpoint Node — evaluates whether a goal is satisfied. The node itself does
 * NOT decide satisfaction; the Runtime's GoalEngine does, and the Runtime records
 * the outcome via `buildCheckpointObservation`. This keeps "mark goal complete"
 * out of both the Planner and the node executor.
 */
import type { GoalStatus, InvestigationNode, CheckpointAction } from "../core/types.ts";
import type { NodeExecutionContext, NodeExecutionResult, NodeExecutor } from "./InvestigationNode.ts";

export interface CheckpointObservationInput {
  goalId: string;
  status: GoalStatus;
  satisfiedClaimTypes: string[];
  missingClaimTypes: string[];
  rationale: string;
}

export function buildCheckpointObservation(input: CheckpointObservationInput): NodeExecutionResult {
  return {
    observationType: "checkpoint_result",
    data: {
      goalId: input.goalId,
      status: input.status,
      satisfiedClaimTypes: input.satisfiedClaimTypes,
      missingClaimTypes: input.missingClaimTypes,
      rationale: input.rationale,
    },
  };
}

/** Passthrough executor for isolation tests; real evaluation happens in GoalEngine. */
export const checkpointExecutor: NodeExecutor = {
  actionType: "checkpoint",
  async execute(node: InvestigationNode, ctx: NodeExecutionContext): Promise<NodeExecutionResult> {
    const action = node.action as CheckpointAction;
    ctx.logger.debug("checkpoint_node.passthrough", { goalId: action.goalId });
    return buildCheckpointObservation({
      goalId: action.goalId,
      status: "waiting",
      satisfiedClaimTypes: [],
      missingClaimTypes: [],
      rationale: "passthrough (evaluated by GoalEngine in the loop)",
    });
  },
};
