/**
 * Common Investigation Node contract, execution context, and the node factory.
 *
 * The FACTORY is the single place where a Planner proposal becomes a real
 * `InvestigationNode`. This enforces the rule "the Planner does not create graph
 * nodes" — the Runtime always goes through `materializeNode`, which stamps the
 * runtime-owned fields (status/createdAt) the Planner is not allowed to set.
 */
import type {
  ClaimTemplate,
  CommandResultData,
  InvestigationNode,
  NodeAction,
  NodeStatus,
  Observation,
  ObservationData,
  ObservationType,
  PlannerNodeProposal,
} from "../core/types.ts";
import type { Clock } from "../util/clock.ts";
import type { IdFactory } from "../util/ids.ts";
import type { Logger } from "../util/logger.ts";
import type { ObservationStore } from "../observations/ObservationStore.ts";
import type { ClaimStore } from "../claims/ClaimStore.ts";
import type { KnowledgeGraph } from "../graphs/KnowledgeGraph.ts";

/** Abstraction over "run a command in the sandbox". Implemented by the runtime. */
export interface CommandRunner {
  run(command: string, workingDirectory: string, timeoutMs: number): Promise<CommandResultData>;
}

/** Everything a leaf node executor needs. Injected by the Runtime. */
export interface NodeExecutionContext {
  investigationId: string;
  repoRoot: string;
  /** repo-relative POSIX paths from the scan (used by discovery). */
  repoFiles: string[];
  allowExecution: boolean;
  observations: ObservationStore;
  claims: ClaimStore;
  knowledge: KnowledgeGraph;
  commandRunner: CommandRunner;
  logger: Logger;
}

/** What an executor returns; the Runtime wraps it into an immutable Observation. */
export interface NodeExecutionResult {
  observationType: ObservationType;
  data: ObservationData;
}

export interface NodeExecutor {
  readonly actionType: NodeAction["type"];
  execute(node: InvestigationNode, ctx: NodeExecutionContext): Promise<NodeExecutionResult>;
}

/**
 * Materialize a validated Planner proposal into a real InvestigationNode.
 * Runtime-owned fields are set here and ONLY here.
 */
export function materializeNode(
  proposal: PlannerNodeProposal,
  deps: { ids: IdFactory; clock: Clock },
): InvestigationNode {
  const nodeId = proposal.nodeId ?? deps.ids.next("node");
  const node: InvestigationNode = {
    nodeId,
    type: proposal.type,
    action: proposal.action,
    hypothesis: proposal.hypothesis,
    successClaim: proposal.successClaim,
    failureClaim: proposal.failureClaim,
    unexpectedAction: proposal.unexpectedAction ?? "escalate_to_planner",
    parentNodeId: proposal.parentNodeId,
    dependencies: proposal.dependencies ?? [],
    goalId: proposal.goalId,
    status: "waiting",
    createdAt: deps.clock.now(),
  };
  return node;
}

/** Build an Observation from an executor result (Runtime-owned constructor). */
export function makeObservation(
  nodeId: string,
  result: NodeExecutionResult,
  deps: { ids: IdFactory; clock: Clock },
): Observation {
  return {
    observationId: deps.ids.next("obs"),
    nodeId,
    type: result.observationType,
    data: result.data,
    createdAt: deps.clock.now(),
    immutable: true,
  };
}

export function claimTemplateEquals(a?: ClaimTemplate, b?: ClaimTemplate): boolean {
  if (!a || !b) return false;
  return a.type === b.type && a.value === b.value;
}

/** Statuses that mean "this node is finished, one way or another". */
export const TERMINAL_STATUSES: readonly NodeStatus[] = ["complete", "failed", "skipped"];
