/**
 * PriorityEngine — decides the ORDER in which ready nodes execute.
 *
 * Deliberately separate from the Planner: the Planner answers "what nodes should
 * exist?", the PriorityEngine answers "which existing ready node runs next?", and
 * the Runtime answers "execute it". This engine never creates or mutates nodes.
 *
 * Ordering (highest priority first):
 *   1. Cheaper/earlier node types before expensive ones — checkpoints and reads
 *      before executes — so the graph converges before spending on execution.
 *   2. Nodes contributing to a goal before goal-less nodes.
 *   3. Stable tie-break by creation order (node id), for determinism.
 */
import type { InvestigationNode, InvestigationNodeType } from "../core/types.ts";

const TYPE_COST: Record<InvestigationNodeType, number> = {
  checkpoint: 0,
  parse: 1,
  read: 2,
  discovery: 3,
  verify: 4,
  synthesize: 5,
  planner: 6,
  execute: 7,
};

export function scoreNode(node: InvestigationNode): number {
  const cost = TYPE_COST[node.type] ?? 9;
  const goalBonus = node.goalId ? -0.5 : 0; // slight preference for goal-linked work
  return cost + goalBonus;
}

/** Return ready nodes in execution order (does not mutate the input array). */
export function orderReadyNodes(ready: InvestigationNode[]): InvestigationNode[] {
  return ready.slice().sort((a, b) => {
    const sa = scoreNode(a);
    const sb = scoreNode(b);
    if (sa !== sb) return sa - sb;
    return a.nodeId.localeCompare(b.nodeId);
  });
}

/** Pick the single next node to run, or undefined if none are ready. */
export function pickNext(ready: InvestigationNode[]): InvestigationNode | undefined {
  return orderReadyNodes(ready)[0];
}
