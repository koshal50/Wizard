/**
 * RuntimeEngine — the OWNER of truth and the driver of the whole investigation.
 *
 * It runs the lifecycle state machine
 *   created → scanning → planning → investigating → converging → reporting →
 *   completed (or cancelled / failed)
 * and the main loop that ties every subsystem together:
 *
 *   scanner → manifest → TechnologyPlanner (goals) →
 *   [ loop: PriorityEngine picks a ready node → NodeRunner executes it →
 *           ResultEvaluator classifies it deterministically →
 *           EvidenceEngine records the implied claim →
 *           GoalEngine re-checks satisfaction;
 *           when nothing is ready, the OngoingPlanner proposes the next nodes;
 *           UNEXPECTED results may escalate to the Planner ] →
 *   converge → result.
 *
 * Invariants enforced here:
 *   - The Planner only ever returns *proposals*; the Runtime materialises them.
 *   - Only UNEXPECTED results can reach the Planner (and only when the node's
 *     unexpectedAction says so and planner budget remains).
 *   - Node + planner budgets are hard ceilings; the loop always terminates.
 */
import type {
  BudgetSummary,
  Goal,
  InvestigationBudget,
  InvestigationNode,
  InvestigationRequest,
  InvestigationResult,
  InvestigationState,
  NodeAction,
  Observation,
  PlannerNodeProposal,
  TechnologyPlan,
} from "../core/types.ts";
import type {
  CommandRunner,
  NodeExecutionContext,
  NodeExecutor,
} from "../nodes/InvestigationNode.ts";
import { buildExecutorRegistry } from "../nodes/registry.ts";
import { InvestigationGraph } from "../graphs/InvestigationGraph.ts";
import { KnowledgeGraph } from "../graphs/KnowledgeGraph.ts";
import { ObservationStore } from "../observations/ObservationStore.ts";
import { ClaimStore } from "../claims/ClaimStore.ts";
import { EvidenceEngine } from "../evidence/EvidenceEngine.ts";
import { GoalEngine } from "./GoalEngine.ts";
import { NodeScheduler } from "./NodeScheduler.ts";
import { EscalationEngine } from "./EscalationEngine.ts";
import { evaluateNode, type EvaluatedNode } from "./ResultEvaluator.ts";
import { pickNext } from "./PriorityEngine.ts";
import { runNode } from "./NodeRunner.ts";
import { buildGoal } from "./goalTemplates.ts";
import { ProcessCommandRunner, DisabledCommandRunner } from "./ProcessCommandRunner.ts";
import { scanRepository, type ScanResult } from "../scanner/fastScanner.ts";
import { buildManifest } from "../manifest/manifest.ts";
import type { RepositoryManifest } from "../manifest/types.ts";
import { buildPlannerContext, type ContextBuilderInputs } from "../planner/PlannerContextBuilder.ts";
import type { InvestigationPlanner } from "../planner/InvestigationPlanner.ts";
import type { ValidationOptions } from "../planner/PlannerValidator.ts";
import type { Clock } from "../util/clock.ts";
import type { IdFactory } from "../util/ids.ts";
import type { Logger } from "../util/logger.ts";

const MAX_ITERATIONS = 10000;
const MAX_PLAN_ATTEMPTS_PER_GOAL = 3;

export interface RuntimeEngineDeps {
  planner: InvestigationPlanner;
  logger: Logger;
  clock: Clock;
  ids: IdFactory;
  /** Defaults to Process/Disabled runner chosen by `allowExecution`. */
  commandRunner?: CommandRunner;
  /** Defaults to the standard leaf-executor registry. */
  registry?: Map<NodeAction["type"], NodeExecutor>;
}

/** All mutable state for a single investigation run. */
interface Session {
  request: InvestigationRequest;
  investigationId: string;
  repoRoot: string;
  repoFiles: string[];
  allowExecution: boolean;
  trustThreshold: number;
  startedAtMs: number;
  budget: InvestigationBudget;
  graph: InvestigationGraph;
  knowledge: KnowledgeGraph;
  observations: ObservationStore;
  claims: ClaimStore;
  goals: Goal[];
  technologyPlan: TechnologyPlan | null;
  manifest: RepositoryManifest;
  priorityByTech: Map<string, string[]>;
  planAttempts: Map<string, number>;
  scheduler: NodeScheduler;
  evidence: EvidenceEngine;
  goalEngine: GoalEngine;
  escalation: EscalationEngine;
  execCtx: NodeExecutionContext;
  registry: Map<NodeAction["type"], NodeExecutor>;
  commandRunner: CommandRunner;
  terminationReason: string;
}

export class RuntimeEngine {
  private readonly deps: RuntimeEngineDeps;

  constructor(deps: RuntimeEngineDeps) {
    this.deps = deps;
  }

  /** Run one investigation to completion and return its full result. */
  async run(request: InvestigationRequest): Promise<InvestigationResult> {
    let session: Session | undefined;
    try {
      this.logState(request.investigationId, "scanning");
      const scan = await scanRepository(request.repositoryPath);
      session = this.createSession(request, scan);

      this.logState(request.investigationId, "planning");
      await this.plan(session);

      this.logState(request.investigationId, "investigating");
      await this.investigate(session);

      this.logState(request.investigationId, "converging");
      this.converge(session);

      this.logState(request.investigationId, "reporting");
      // Report rendering + persistence are performed by the caller's
      // ReportGenerator using the returned InvestigationResult.

      this.logState(request.investigationId, "completed");
      return this.buildResult(session, "completed");
    } catch (e) {
      const message = (e as Error).message;
      this.deps.logger.error("runtime.failed", { investigationId: request.investigationId, error: message });
      if (!session) return this.failedShell(request, message);
      session.terminationReason = `engine error: ${message}`;
      return this.buildResult(session, "failed");
    }
  }

  private logState(investigationId: string, to: InvestigationState): void {
    this.deps.logger.info("runtime.state", { investigationId, state: to });
  }

  // ── session construction ─────────────────────────────────────────────────

  private createSession(request: InvestigationRequest, scan: ScanResult): Session {
    const cfg = request.configuration ?? {};
    const allowExecution = cfg.allowExecution ?? true;
    const trustThreshold = cfg.goalTrustThreshold ?? 0.6;
    const manifest = buildManifest(scan);

    const graph = new InvestigationGraph();
    const knowledge = new KnowledgeGraph();
    const observations = new ObservationStore();
    const claims = new ClaimStore();

    const { logger, ids, clock } = this.deps;

    const commandRunner =
      this.deps.commandRunner ?? (allowExecution ? new ProcessCommandRunner({ clock }) : new DisabledCommandRunner());
    const registry = this.deps.registry ?? buildExecutorRegistry();

    const evidence = new EvidenceEngine({
      claims,
      knowledge,
      ids,
      clock,
      logger,
      investigationId: request.investigationId,
    });
    const goalEngine = new GoalEngine(claims, { defaultTrustThreshold: trustThreshold });
    const scheduler = new NodeScheduler({
      graph,
      ids,
      clock,
      logger,
      repoRoot: scan.rootPath,
      allowExecution,
    });
    const escalation = new EscalationEngine({ planner: this.deps.planner, logger });

    const execCtx: NodeExecutionContext = {
      investigationId: request.investigationId,
      repoRoot: scan.rootPath,
      repoFiles: scan.files.map((f) => f.relativePath),
      allowExecution,
      observations,
      claims,
      knowledge,
      commandRunner,
      logger,
    };

    return {
      request,
      investigationId: request.investigationId,
      repoRoot: scan.rootPath,
      repoFiles: execCtx.repoFiles,
      allowExecution,
      trustThreshold,
      startedAtMs: Date.parse(clock.now()),
      budget: { ...request.budget },
      graph,
      knowledge,
      observations,
      claims,
      goals: [],
      technologyPlan: null,
      manifest,
      priorityByTech: new Map(),
      planAttempts: new Map(),
      scheduler,
      evidence,
      goalEngine,
      escalation,
      execCtx,
      registry,
      commandRunner,
      terminationReason: "completed normally",
    };
  }

  // ── planning: manifest → technologies → goals ────────────────────────────

  private async plan(s: Session): Promise<void> {
    const plan = await this.deps.planner.planTechnologies(s.manifest);
    this.incrementPlannerCall(s);
    s.technologyPlan = plan;

    const targets = s.request.investigationTargets.map((t) => t.toLowerCase());
    for (const tech of plan.technologies) {
      s.priorityByTech.set(tech.name, tech.priorityFiles ?? []);
      const goalNames = tech.initialGoals.length ? tech.initialGoals : ["Verify Runtime"];
      for (const goalName of goalNames) {
        if (targets.length && !this.goalMatchesTargets(goalName, tech.name, targets)) continue;
        s.goals.push(buildGoal(goalName, tech.name, this.deps.ids));
      }
    }

    // If nothing matched (or the plan was empty), fall back to the raw targets so
    // the investigation still has something concrete to pursue.
    if (s.goals.length === 0) {
      const fallbackTargets = s.request.investigationTargets.length
        ? s.request.investigationTargets
        : ["runtime"];
      for (const target of fallbackTargets) {
        s.goals.push(buildGoal(`Verify ${capitalize(target)}`, "General", this.deps.ids));
      }
    }

    this.deps.logger.info("runtime.goals", {
      investigationId: s.investigationId,
      goals: s.goals.map((g) => ({ id: g.goalId, name: g.name, tech: g.technology })),
    });
  }

  private goalMatchesTargets(goalName: string, tech: string, targets: string[]): boolean {
    const hay = `${goalName} ${tech}`.toLowerCase();
    return targets.some((t) => hay.includes(t));
  }

  // ── investigating: the main loop ──────────────────────────────────────────

  private async investigate(s: Session): Promise<void> {
    let iterations = 0;

    while (true) {
      if (++iterations > MAX_ITERATIONS) {
        s.terminationReason = "iteration ceiling reached";
        this.deps.logger.warn("runtime.iteration_ceiling", { investigationId: s.investigationId });
        return;
      }
      if (this.budgetExhausted(s)) {
        s.terminationReason = "node execution budget exhausted";
        return;
      }
      if (this.timeExceeded(s)) {
        s.terminationReason = "execution time budget exceeded";
        return;
      }

      // Refresh goal statuses from the current knowledge before deciding.
      this.refreshGoals(s);
      if (this.allGoalsResolved(s)) {
        s.terminationReason = "all goals resolved";
        return;
      }

      const ready = s.scheduler.readyNodes();
      if (ready.length > 0) {
        const node = pickNext(ready)!;
        await this.executeReadyNode(s, node);
        continue;
      }

      // No ready work: ask the Planner for the next batch for an unresolved goal.
      const progressed = await this.planNextForOpenGoal(s);
      if (!progressed) {
        s.terminationReason = "no further nodes could be planned";
        return;
      }
    }
  }

  private async executeReadyNode(s: Session, node: InvestigationNode): Promise<void> {
    s.graph.updateNode(node.nodeId, { status: "running" });

    const observation = await runNode(node, s.execCtx, {
      registry: s.registry,
      ids: this.deps.ids,
      clock: this.deps.clock,
    });
    s.observations.add(observation);
    s.budget.executionsUsed += 1;

    const evaluated = evaluateNode(node, observation);
    this.deps.logger.info("runtime.node.evaluated", {
      nodeId: node.nodeId,
      type: node.type,
      outcome: evaluated.outcome,
      reasonCode: evaluated.reasonCode,
    });

    // Record the claim implied by a deterministic SUCCESS/FAILURE.
    if (evaluated.outcome !== "UNEXPECTED" && evaluated.claimTemplate) {
      s.evidence.recordClaim(evaluated.claimTemplate, observation, node.nodeId);
    }

    const finalStatus = evaluated.outcome === "FAILURE" ? "failed" : "complete";
    s.graph.updateNode(node.nodeId, {
      status: finalStatus,
      observationId: observation.observationId,
      completedAt: this.deps.clock.now(),
      error: evaluated.outcome === "UNEXPECTED" ? { message: evaluated.reason } : undefined,
    });

    this.refreshGoals(s);

    if (evaluated.outcome === "UNEXPECTED") {
      await this.handleUnexpected(s, node, observation, evaluated);
    }

    s.scheduler.refreshReadiness();
  }

  // ── escalation on UNEXPECTED ──────────────────────────────────────────────

  private async handleUnexpected(
    s: Session,
    node: InvestigationNode,
    observation: Observation,
    evaluated: EvaluatedNode,
  ): Promise<void> {
    const action = node.unexpectedAction ?? "escalate_to_planner";

    // "record_only" nodes never call the Planner — a key LLM-minimising lever.
    if (action === "record_only") {
      this.deps.logger.info("runtime.unexpected.record_only", { nodeId: node.nodeId });
      return;
    }

    // Honest downgrade: if execution is globally disabled, an execute node that
    // could not run is not a surprise worth an LLM call — record and move on so
    // the goal can be reported "unsatisfiable" rather than fabricated.
    if (evaluated.reasonCode === "execution_disabled" && !s.allowExecution) {
      this.deps.logger.info("runtime.unexpected.exec_disabled_downgrade", { nodeId: node.nodeId });
      return;
    }

    if (!this.plannerBudgetRemaining(s)) {
      this.deps.logger.warn("runtime.unexpected.no_planner_budget", { nodeId: node.nodeId });
      return;
    }

    const goal = this.goalForNode(s, node);
    if (!goal) {
      this.deps.logger.warn("runtime.unexpected.no_goal", { nodeId: node.nodeId });
      return;
    }

    const built = this.buildContext(s, goal);
    const batch = await s.escalation.escalate({
      investigationId: s.investigationId,
      node,
      observation,
      currentGoal: goal,
      budget: built.plannerContext.budget,
      heuristicContext: built.heuristicContext,
      validation: this.validationOptions(s),
    });
    this.incrementPlannerCall(s);

    this.insertBatch(s, batch.accepted, node.nodeId);
  }

  // ── planning the next batch for an open goal ───────────────────────────────

  private async planNextForOpenGoal(s: Session): Promise<boolean> {
    const goal = this.nextOpenGoal(s);
    if (!goal) return false;

    const attempts = s.planAttempts.get(goal.goalId) ?? 0;
    if (attempts >= MAX_PLAN_ATTEMPTS_PER_GOAL) {
      this.markUnsatisfiable(s, goal, "planner produced no new work after repeated attempts");
      return true; // progress = we resolved the goal (as unsatisfiable)
    }
    if (!this.plannerBudgetRemaining(s)) {
      this.markUnsatisfiable(s, goal, "planner call budget exhausted");
      return true;
    }

    s.planAttempts.set(goal.goalId, attempts + 1);
    const built = this.buildContext(s, goal);
    const batch = await this.deps.planner.planNext(built, this.validationOptions(s));
    this.incrementPlannerCall(s);

    const inserted = this.insertBatch(s, batch.accepted);
    if (inserted === 0) {
      // Nothing new to do for this goal — it cannot be satisfied with what we have.
      this.markUnsatisfiable(s, goal, batch.rationale ?? "planner returned no actionable nodes");
    }
    return true;
  }

  private insertBatch(s: Session, proposals: PlannerNodeProposal[], parentNodeId?: string): number {
    if (proposals.length === 0) return 0;
    const withParent = parentNodeId
      ? proposals.map((p) => ({ ...p, parentNodeId: p.parentNodeId ?? parentNodeId }))
      : proposals;
    const outcome = s.scheduler.insertProposals(withParent, this.budgetRemainingNodes(s));
    if (outcome.rejected.length) {
      this.deps.logger.warn("runtime.insert.rejected", {
        reasons: outcome.rejected.map((r) => r.reason),
      });
    }
    return outcome.inserted.length;
  }

  // ── goals ─────────────────────────────────────────────────────────────────

  private refreshGoals(s: Session): void {
    for (const goal of s.goals) {
      if (goal.status === "satisfied" || goal.status === "unsatisfiable") continue;
      const evaluation = s.goalEngine.evaluate(goal);
      if (evaluation.status !== goal.status) {
        goal.status = evaluation.status;
        this.deps.logger.info("runtime.goal.status", {
          goalId: goal.goalId,
          status: goal.status,
          rationale: evaluation.rationale,
        });
      }
    }
  }

  private markUnsatisfiable(s: Session, goal: Goal, reason: string): void {
    goal.status = "unsatisfiable";
    this.deps.logger.warn("runtime.goal.unsatisfiable", { goalId: goal.goalId, reason });
  }

  private nextOpenGoal(s: Session): Goal | undefined {
    return s.goals.find((g) => g.status === "waiting" || g.status === "in_progress");
  }

  private allGoalsResolved(s: Session): boolean {
    return s.goals.every((g) => g.status === "satisfied" || g.status === "unsatisfiable");
  }

  private goalForNode(s: Session, node: InvestigationNode): Goal | undefined {
    if (node.goalId) {
      const byId = s.goals.find((g) => g.goalId === node.goalId);
      if (byId) return byId;
    }
    return this.nextOpenGoal(s);
  }

  // ── context + validation ──────────────────────────────────────────────────

  private buildContext(s: Session, goal: Goal): ReturnType<typeof buildPlannerContext> {
    const inputs: ContextBuilderInputs = {
      investigationId: s.investigationId,
      userIntent: s.request.userIntent,
      currentGoal: goal,
      knowledge: s.knowledge,
      claims: s.claims,
      graph: s.graph,
      observations: s.observations,
      repositoryName: s.manifest.repositoryName,
      keyFiles: s.manifest.keyFiles.map((k) => k.path),
      priorityFiles: s.priorityByTech.get(goal.technology) ?? [],
      budget: s.budget,
      allowExecution: s.allowExecution,
    };
    return buildPlannerContext(inputs);
  }

  private validationOptions(s: Session): ValidationOptions {
    return {
      repoRoot: s.repoRoot,
      budgetRemaining: this.budgetRemainingNodes(s),
      allowExecution: s.allowExecution,
    };
  }

  // ── budgets ───────────────────────────────────────────────────────────────

  private budgetRemainingNodes(s: Session): number {
    return Math.max(0, s.budget.maxNodeExecutions - s.budget.executionsUsed);
  }

  private budgetExhausted(s: Session): boolean {
    return this.budgetRemainingNodes(s) <= 0;
  }

  private plannerBudgetRemaining(s: Session): boolean {
    if (s.budget.maxPlannerCalls === undefined) return true;
    return (s.budget.plannerCallsUsed ?? 0) < s.budget.maxPlannerCalls;
  }

  private incrementPlannerCall(s: Session): void {
    s.budget.plannerCallsUsed = (s.budget.plannerCallsUsed ?? 0) + 1;
  }

  private timeExceeded(s: Session): boolean {
    const cap = s.budget.maxExecutionTimeMs;
    if (cap === undefined) return false;
    const elapsed = Date.parse(this.deps.clock.now()) - s.startedAtMs;
    return elapsed >= cap;
  }

  // ── converge + result ─────────────────────────────────────────────────────

  private converge(s: Session): void {
    this.refreshGoals(s);
    // Any goal still open at convergence (loop ended on budget/time) is recorded
    // as unsatisfiable so the report never over-claims success.
    for (const goal of s.goals) {
      if (goal.status === "waiting" || goal.status === "in_progress") {
        this.markUnsatisfiable(s, goal, "investigation ended before goal was satisfied");
      }
    }
  }

  private buildResult(s: Session, state: InvestigationState): InvestigationResult {
    const goalsSatisfied = s.goals.filter((g) => g.status === "satisfied").length;
    return {
      investigationId: s.investigationId,
      state,
      technologyPlan: s.technologyPlan,
      investigationGraph: s.graph.snapshot(),
      knowledgeGraph: s.knowledge.snapshot(),
      observations: s.observations.all(),
      claims: s.claims.all(),
      goals: s.goals,
      statistics: {
        nodesExecuted: s.budget.executionsUsed,
        plannerCalls: s.budget.plannerCallsUsed ?? 0,
        claimsCreated: s.claims.size(),
        observationsCreated: s.observations.size(),
        goalsSatisfied,
        goalsTotal: s.goals.length,
      },
      terminationReason: s.terminationReason,
    };
  }

  private failedShell(request: InvestigationRequest, message: string): InvestigationResult {
    return {
      investigationId: request.investigationId,
      state: "failed",
      technologyPlan: null,
      investigationGraph: { nodes: [], edges: [] },
      knowledgeGraph: { claims: [], relationships: [] },
      observations: [],
      claims: [],
      goals: [],
      statistics: {
        nodesExecuted: 0,
        plannerCalls: 0,
        claimsCreated: 0,
        observationsCreated: 0,
        goalsSatisfied: 0,
        goalsTotal: 0,
      },
      terminationReason: `failed before session start: ${message}`,
    };
  }
}

function capitalize(s: string): string {
  return s.length ? s.charAt(0).toUpperCase() + s.slice(1) : s;
}

/** Convenience: build a BudgetSummary from a raw budget (used by callers/tests). */
export function summarizeBudget(budget: InvestigationBudget): BudgetSummary {
  const plannerRemaining =
    budget.maxPlannerCalls === undefined ? null : Math.max(0, budget.maxPlannerCalls - (budget.plannerCallsUsed ?? 0));
  return {
    nodeExecutionsRemaining: Math.max(0, budget.maxNodeExecutions - budget.executionsUsed),
    plannerCallsRemaining: plannerRemaining,
  };
}



