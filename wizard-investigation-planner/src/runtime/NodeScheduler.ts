/**
 * NodeScheduler — owns INSERTION and READINESS in the Investigation Graph.
 *
 * Responsibilities:
 *   1. Materialise validated Planner proposals into real nodes (via the node
 *      factory) and insert them, RE-CHECKING security at insert time (defence in
 *      depth: even if a proposal slipped through, the scheduler refuses to insert
 *      an unsafe read/execute) and REJECTING any insertion that would create a
 *      dependency cycle.
 *   2. Recompute node readiness: a `waiting` node becomes `ready` when all its
 *      dependencies are `complete`, or `blocked` if any dependency failed.
 *
 * The scheduler never executes nodes and never evaluates results.
 */
import type { InvestigationNode, PlannerNodeProposal } from "../core/types.ts";
import { InvestigationGraph } from "../graphs/InvestigationGraph.ts";
import { materializeNode } from "../nodes/InvestigationNode.ts";
import type { Clock } from "../util/clock.ts";
import type { IdFactory } from "../util/ids.ts";
import type { Logger } from "../util/logger.ts";
import { validateProposal } from "../planner/PlannerValidator.ts";

export interface SchedulerDeps {
  graph: InvestigationGraph;
  ids: IdFactory;
  clock: Clock;
  logger: Logger;
  repoRoot: string;
  allowExecution: boolean;
}

export interface InsertOutcome {
  inserted: InvestigationNode[];
  rejected: { proposal: PlannerNodeProposal; reason: string }[];
}

export class NodeScheduler {
  private readonly deps: SchedulerDeps;

  constructor(deps: SchedulerDeps) {
    this.deps = deps;
  }

  /**
   * Insert a batch of validated proposals. Each is re-checked for safety and for
   * cycle-freedom; failures are reported and skipped, not thrown.
   */
  insertProposals(proposals: PlannerNodeProposal[], budgetRemaining: number): InsertOutcome {
    const { graph, ids, clock, logger } = this.deps;
    const inserted: InvestigationNode[] = [];
    const rejected: InsertOutcome["rejected"] = [];

    for (const proposal of proposals) {
      if (inserted.length >= budgetRemaining) {
        rejected.push({ proposal, reason: "node budget exhausted" });
        continue;
      }
      // Defence in depth: re-validate security/semantics at insert time.
      const reason = validateProposal(proposal, {
        repoRoot: this.deps.repoRoot,
        budgetRemaining,
        allowExecution: this.deps.allowExecution,
      });
      if (reason) {
        rejected.push({ proposal, reason });
        continue;
      }

      const node = materializeNode(proposal, { ids, clock });
      // Only keep dependencies that reference existing nodes (or the same batch).
      node.dependencies = node.dependencies.filter(
        (dep) => graph.hasNode(dep) || inserted.some((n) => n.nodeId === dep),
      );

      try {
        graph.addNode(node);
      } catch (e) {
        rejected.push({ proposal, reason: `insert failed: ${(e as Error).message}` });
        continue;
      }

      // Cycle guard: if this insertion introduced a cycle, roll it back.
      const cycle = graph.findDependencyCycle();
      if (cycle) {
        graph.updateNode(node.nodeId, { status: "skipped", error: { message: "dependency cycle" } });
        rejected.push({ proposal, reason: `dependency cycle: ${cycle.join(" -> ")}` });
        logger.warn("scheduler.cycle_rejected", { nodeId: node.nodeId, cycle });
        continue;
      }

      inserted.push(node);
    }

    this.refreshReadiness();
    if (inserted.length) {
      logger.debug("scheduler.inserted", { count: inserted.length, ids: inserted.map((n) => n.nodeId) });
    }
    return { inserted, rejected };
  }

  /** Recompute waiting → ready/blocked transitions across the whole graph. */
  refreshReadiness(): void {
    const { graph } = this.deps;
    for (const node of graph.allNodes()) {
      if (node.status !== "waiting" && node.status !== "blocked" && node.status !== "ready") continue;
      if (node.status === "ready" || node.status === "blocked") {
        // Re-derive from scratch so a repaired dependency can unblock.
      }
      if (graph.hasBlockedDependency(node.nodeId)) {
        if (node.status !== "blocked") graph.updateNode(node.nodeId, { status: "blocked" });
        continue;
      }
      if (graph.dependenciesSatisfied(node.nodeId)) {
        if (node.status !== "ready") graph.updateNode(node.nodeId, { status: "ready" });
      } else {
        if (node.status !== "waiting") graph.updateNode(node.nodeId, { status: "waiting" });
      }
    }
  }

  /** Nodes eligible to run right now. */
  readyNodes(): InvestigationNode[] {
    this.refreshReadiness();
    return this.deps.graph.nodesByStatus("ready");
  }
}
