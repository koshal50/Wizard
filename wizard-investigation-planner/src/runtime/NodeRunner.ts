/**
 * NodeRunner — executes ONE node and produces its immutable Observation.
 *
 * It looks up the leaf executor for the node's action type, runs it inside the
 * provided `NodeExecutionContext`, and wraps the result into an Observation via
 * the runtime-owned `makeObservation` factory. A thrown executor error is turned
 * into an `error` observation (never a crash) so the evaluator can classify it as
 * UNEXPECTED and the loop can continue.
 *
 * Planner and Checkpoint nodes are NOT run here — the Runtime orchestrates their
 * side effects directly (they need the Planner/GoalEngine). This runner handles
 * the leaf types: discovery / read / execute / parse / verify / synthesize.
 */
import type { InvestigationNode, Observation } from "../core/types.ts";
import {
  makeObservation,
  type NodeExecutionContext,
  type NodeExecutor,
} from "../nodes/InvestigationNode.ts";
import type { Clock } from "../util/clock.ts";
import type { IdFactory } from "../util/ids.ts";

export interface NodeRunnerDeps {
  registry: Map<string, NodeExecutor>;
  ids: IdFactory;
  clock: Clock;
}

export async function runNode(
  node: InvestigationNode,
  ctx: NodeExecutionContext,
  deps: NodeRunnerDeps,
): Promise<Observation> {
  const executor = deps.registry.get(node.action.type);
  if (!executor) {
    return makeObservation(
      node.nodeId,
      { observationType: "error", data: { message: `no executor for action ${node.action.type}` } },
      deps,
    );
  }

  try {
    const result = await executor.execute(node, ctx);
    return makeObservation(node.nodeId, result, deps);
  } catch (e) {
    ctx.logger.warn("node.execute.threw", { nodeId: node.nodeId, error: (e as Error).message });
    return makeObservation(
      node.nodeId,
      { observationType: "error", data: { message: (e as Error).message, nodeId: node.nodeId } },
      deps,
    );
  }
}
