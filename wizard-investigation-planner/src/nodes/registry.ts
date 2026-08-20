/**
 * Registry of leaf-node executors. Planner + Checkpoint nodes are intentionally
 * NOT executed through this generic path in the loop — the Runtime orchestrates
 * their side effects — but their passthrough executors are registered so they can
 * be exercised in isolation tests.
 */
import type { NodeAction } from "../core/types.ts";
import type { NodeExecutor } from "./InvestigationNode.ts";
import { discoveryExecutor } from "./DiscoveryNode.ts";
import { readExecutor } from "./ReadNode.ts";
import { executeExecutor } from "./ExecuteNode.ts";
import { parseExecutor } from "./ParseNode.ts";
import { verifyExecutor } from "./VerifyNode.ts";
import { synthesizeExecutor } from "./SynthesizeNode.ts";
import { plannerExecutor } from "./PlannerNode.ts";
import { checkpointExecutor } from "./CheckpointNode.ts";

export const LEAF_EXECUTORS: NodeExecutor[] = [
  discoveryExecutor,
  readExecutor,
  executeExecutor,
  parseExecutor,
  verifyExecutor,
  synthesizeExecutor,
  plannerExecutor,
  checkpointExecutor,
];

export function buildExecutorRegistry(
  executors: NodeExecutor[] = LEAF_EXECUTORS,
): Map<NodeAction["type"], NodeExecutor> {
  const map = new Map<NodeAction["type"], NodeExecutor>();
  for (const ex of executors) map.set(ex.actionType, ex);
  return map;
}
