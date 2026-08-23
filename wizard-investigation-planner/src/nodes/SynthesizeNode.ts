/**
 * Synthesize Node — combines several observations into a single synthesized
 * finding. Deterministic aggregation only (counts/summaries); it produces a
 * synthesis_result Observation. The actual Claim (if any) is still created by
 * the Runtime from the node's successClaim template — the node never writes to
 * the Knowledge Graph directly.
 */
import type { InvestigationNode, SynthesizeAction } from "../core/types.ts";
import type { NodeExecutionContext, NodeExecutionResult, NodeExecutor } from "./InvestigationNode.ts";

export const synthesizeExecutor: NodeExecutor = {
  actionType: "synthesize",
  async execute(node: InvestigationNode, ctx: NodeExecutionContext): Promise<NodeExecutionResult> {
    const action = node.action as SynthesizeAction;
    const observations = action.observationIds
      .map((id) => ctx.observations.get(id))
      .filter((o): o is NonNullable<typeof o> => Boolean(o));

    const summary = observations.map((o) => ({
      observationId: o.observationId,
      type: o.type,
      nodeId: o.nodeId,
    }));

    ctx.logger.debug("synthesize.executed", { inputs: observations.length });
    return {
      observationType: "synthesis_result",
      data: {
        inputObservationIds: action.observationIds,
        inputCount: observations.length,
        summary,
      },
    };
  },
};
