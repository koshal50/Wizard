/**
 * Planner Node — a node whose "execution" is an invocation of the LLM Planner to
 * create the next investigation node(s).
 *
 * Unlike leaf nodes, the Planner Node's side effect (calling the Planner and
 * inserting the resulting proposals) is orchestrated by the Runtime, because it
 * needs access to the Planner + Scheduler which are not part of the leaf
 * NodeExecutionContext. This module provides the Observation shape the Runtime
 * records after that invocation, and a passthrough executor used only when a
 * Planner Node is executed outside the loop (e.g. in isolation tests).
 */
import type { InvestigationNode, PlannerAction } from "../core/types.ts";
import type { NodeExecutionContext, NodeExecutionResult, NodeExecutor } from "./InvestigationNode.ts";

export interface PlannerObservationInput {
  reason: string;
  createdNodeIds: string[];
  plannerCalled: boolean;
  rationale?: string;
}

export function buildPlannerObservation(input: PlannerObservationInput): NodeExecutionResult {
  return {
    observationType: "planner_result",
    data: {
      reason: input.reason,
      createdNodeIds: input.createdNodeIds,
      plannerCalled: input.plannerCalled,
      rationale: input.rationale ?? null,
    },
  };
}

/** Passthrough executor: records the intent but creates no nodes on its own. */
export const plannerExecutor: NodeExecutor = {
  actionType: "planner",
  async execute(node: InvestigationNode, ctx: NodeExecutionContext): Promise<NodeExecutionResult> {
    const action = node.action as PlannerAction;
    ctx.logger.debug("planner_node.passthrough", { reason: action.reason });
    return buildPlannerObservation({ reason: action.reason, createdNodeIds: [], plannerCalled: false });
  },
};
