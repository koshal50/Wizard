/**
 * PlannerContextBuilder — assembles the PROGRESSIVE, compact context handed to
 * the Planner. This is where the "3-tier context / never the whole repo" rule
 * lives:
 *
 *   Tier 1: the manifest key files (names only).
 *   Tier 2: short excerpts of files that have actually been read.
 *   Tier 3: summaries of recent observations (execution/parse results).
 *
 * It produces two artifacts from the same underlying state:
 *   - `plannerContext`: the human/LLM-readable `PlannerContext` used to render
 *     the natural-language prompt.
 *   - `heuristicContext`: the structured payload the offline HeuristicLLMProvider
 *     consumes to make the same decision deterministically.
 *
 * It is READ-ONLY over the graphs/stores — the context builder never mutates
 * anything and never creates nodes/claims.
 */
import type {
  BudgetSummary,
  FileContentData,
  Goal,
  InvestigationBudget,
  InvestigationNode,
  InvestigationNodeSummary,
  Observation,
  ObservationSummary,
  OpenQuestion,
  PlannerContext,
  RelevantClaimSummary,
  UserIntent,
} from "../core/types.ts";
import type { KnowledgeGraph } from "../graphs/KnowledgeGraph.ts";
import type { ClaimStore } from "../claims/ClaimStore.ts";
import type { InvestigationGraph } from "../graphs/InvestigationGraph.ts";
import type { ObservationStore } from "../observations/ObservationStore.ts";

const MAX_RECENT_NODES = 8;
const MAX_RECENT_OBSERVATIONS = 8;
const EXCERPT_CHARS = 160;

export interface ContextBuilderInputs {
  investigationId: string;
  userIntent: UserIntent;
  currentGoal: Goal;
  knowledge: KnowledgeGraph;
  claims: ClaimStore;
  graph: InvestigationGraph;
  observations: ObservationStore;
  repositoryName: string;
  keyFiles: string[];
  priorityFiles: string[];
  budget: InvestigationBudget;
  allowExecution: boolean;
}

export interface BuiltContext {
  plannerContext: PlannerContext;
  heuristicContext: Record<string, unknown>;
}

export function buildPlannerContext(inputs: ContextBuilderInputs): BuiltContext {
  const { currentGoal } = inputs;
  const observations = inputs.observations.all();

  const readFiles = collectReadFiles(observations);
  const { fileObservationIds, parsedObservationIds } = collectObservationIndex(observations, inputs.observations);
  const missing = missingRequirements(inputs);

  const budgetSummary = summarizeBudget(inputs.budget);

  const plannerContext: PlannerContext = {
    investigationId: inputs.investigationId,
    userIntent: inputs.userIntent,
    currentGoal: {
      goalId: currentGoal.goalId,
      name: currentGoal.name,
      technology: currentGoal.technology,
      status: currentGoal.status,
      requirements: currentGoal.requirements.map((r) => r.description),
    },
    knowledgeGraph: { claims: summarizeClaims(inputs.knowledge) },
    recentInvestigationNodes: summarizeRecentNodes(inputs.graph),
    openQuestions: missing.map<OpenQuestion>((r) => ({
      question: r.description,
      missingClaimType: r.claimType,
    })),
    repositoryContext: {
      repositoryName: inputs.repositoryName,
      keyFiles: inputs.keyFiles.slice(0, 20),
      readFiles,
    },
    recentObservations: summarizeRecentObservations(observations),
    budget: budgetSummary,
  };

  const heuristicContext: Record<string, unknown> = {
    goalTechnology: currentGoal.technology,
    allowExecution: inputs.allowExecution,
    missingRequirements: missing.map((r) => ({
      claimType: r.claimType,
      description: r.description,
      expectedValue: r.expectedValue,
    })),
    priorityFiles: inputs.priorityFiles,
    fileObservationIds,
    parsedObservationIds,
  };

  return { plannerContext, heuristicContext };
}

// ── helpers ───────────────────────────────────────────────────────────────────

function summarizeClaims(knowledge: KnowledgeGraph): RelevantClaimSummary[] {
  return knowledge.allClaims().map((c) => ({ type: c.type, value: c.value, trust: c.trust }));
}

function summarizeRecentNodes(graph: InvestigationGraph): InvestigationNodeSummary[] {
  const all = graph.allNodes();
  return all.slice(-MAX_RECENT_NODES).map((n) => ({
    nodeId: n.nodeId,
    type: n.type,
    action: compactAction(n),
    hypothesis: n.hypothesis,
    status: n.status,
  }));
}

function summarizeRecentObservations(observations: Observation[]): ObservationSummary[] {
  return observations.slice(-MAX_RECENT_OBSERVATIONS).map((o) => ({
    observationId: o.observationId,
    type: o.type,
    summary: summarizeObservation(o),
  }));
}

function summarizeObservation(o: Observation): string {
  const d = o.data as Record<string, unknown>;
  switch (o.type) {
    case "file_content":
      return `${String(d.filePath)} (${d.exists ? `${d.bytes}B` : "missing"})`;
    case "command_result":
      return `\`${String(d.command)}\` exit=${d.exitCode === null ? "n/a" : d.exitCode}`;
    case "parse_result":
      return `parse(${String(d.parser)}) ok=${d.ok}`;
    case "discovery_result":
      return `discovery matched ${Array.isArray(d.matches) ? d.matches.length : 0}`;
    default:
      return o.type;
  }
}

function collectReadFiles(observations: Observation[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const o of observations) {
    if (o.type !== "file_content") continue;
    const d = o.data as FileContentData;
    if (!d.exists) continue;
    out[d.filePath] = excerpt(d.content);
  }
  return out;
}

function collectObservationIndex(
  observations: Observation[],
  store: ObservationStore,
): { fileObservationIds: Record<string, string>; parsedObservationIds: Record<string, string> } {
  const fileObservationIds: Record<string, string> = {};
  const parsedObservationIds: Record<string, string> = {};

  for (const o of observations) {
    if (o.type === "file_content") {
      const d = o.data as FileContentData;
      if (d.exists) fileObservationIds[d.filePath] = o.observationId;
    }
  }
  for (const o of observations) {
    if (o.type !== "parse_result") continue;
    const d = o.data as { sourceObservationId?: string };
    if (!d.sourceObservationId) continue;
    const source = store.get(d.sourceObservationId);
    if (source && source.type === "file_content") {
      const fc = source.data as FileContentData;
      parsedObservationIds[fc.filePath] = o.observationId;
    }
  }
  return { fileObservationIds, parsedObservationIds };
}

interface MissingRequirement {
  claimType: string;
  description: string;
  expectedValue?: string;
}

function missingRequirements(inputs: ContextBuilderInputs): MissingRequirement[] {
  const out: MissingRequirement[] = [];
  for (const req of inputs.currentGoal.requirements) {
    const claim = inputs.claims.findByType(req.claimType);
    const satisfied =
      claim !== undefined &&
      (req.expectedValue === undefined || claim.value === req.expectedValue) &&
      (req.notValue === undefined || claim.value !== req.notValue) &&
      (req.minTrust === undefined || claim.trust >= req.minTrust);
    if (!satisfied) {
      out.push({ claimType: req.claimType, description: req.description, expectedValue: req.expectedValue });
    }
  }
  return out;
}

function summarizeBudget(budget: InvestigationBudget): BudgetSummary {
  const plannerRemaining =
    budget.maxPlannerCalls === undefined ? null : budget.maxPlannerCalls - (budget.plannerCallsUsed ?? 0);
  return {
    nodeExecutionsRemaining: Math.max(0, budget.maxNodeExecutions - budget.executionsUsed),
    plannerCallsRemaining: plannerRemaining === null ? null : Math.max(0, plannerRemaining),
  };
}

function excerpt(content: string): string {
  const oneLine = content.replace(/\s+/g, " ").trim();
  return oneLine.length > EXCERPT_CHARS ? oneLine.slice(0, EXCERPT_CHARS) + "…" : oneLine;
}

function compactAction(n: InvestigationNode): string {
  const a = n.action;
  switch (a.type) {
    case "discovery":
      return `discover "${a.pattern}"`;
    case "read":
      return `read ${a.filePath}`;
    case "execute":
      return `exec \`${a.command}\``;
    case "parse":
      return `parse(${a.parser})`;
    case "verify":
      return "verify";
    case "synthesize":
      return "synthesize";
    case "planner":
      return "plan";
    case "checkpoint":
      return `checkpoint ${a.goalId}`;
    default:
      return "";
  }
}
