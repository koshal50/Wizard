/**
 * Wizard — Core shared types.
 *
 * This is the single source of truth for every data shape that crosses a module
 * boundary. It encodes the architectural invariants of the two-graph design:
 *
 *   - The PLANNER only ever produces `PlannerNodeProposal` / `TechnologyPlan`
 *     objects. It never constructs an `InvestigationNode`, `Observation`, or
 *     `Claim` directly — the Runtime does that.
 *   - `Observation` and `Claim` are immutable once created.
 *   - Every `Claim` carries `ClaimProvenance` pointing back to the node +
 *     observation that produced it.
 *
 * NOTE: this project runs `.ts` directly on Node's native type-stripping loader,
 * so this file (and all others) uses ERASABLE syntax only — no `enum`, no
 * `namespace`, no constructor parameter properties. Unions + `as const` objects
 * are used in place of enums.
 */

// ─────────────────────────────────────────────────────────────────────────────
// Identifiers
// ─────────────────────────────────────────────────────────────────────────────

export type InvestigationId = string;
export type NodeId = string;
export type ObservationId = string;
export type ClaimId = string;
export type GoalId = string;
export type RelationshipId = string;

/** ISO-8601 timestamp string. */
export type Timestamp = string;

// ─────────────────────────────────────────────────────────────────────────────
// Investigation state machine (owned exclusively by the Runtime)
// ─────────────────────────────────────────────────────────────────────────────

export type InvestigationState =
  | "created"
  | "scanning"
  | "planning"
  | "investigating"
  | "converging"
  | "reporting"
  | "completed"
  | "cancelled"
  | "failed";

export type UserIntent = "investigate" | "verify" | "explain" | "report";

export type Confidence = "high" | "medium" | "low";

// ─────────────────────────────────────────────────────────────────────────────
// Investigation request / budget
// ─────────────────────────────────────────────────────────────────────────────

export interface InvestigationRequest {
  investigationId: InvestigationId;
  userIntent: UserIntent;
  repositoryPath: string;
  /** e.g. ["runtime", "dependencies"] — what the user asked to verify. */
  investigationTargets: string[];
  budget: InvestigationBudget;
  configuration?: InvestigationConfiguration;
}

export interface InvestigationConfiguration {
  /** Allow Execute nodes to actually spawn processes. Default true. */
  allowExecution?: boolean;
  /** Write verification_report.md + snapshot to disk. Default true. */
  persist?: boolean;
  /** Directory for artifacts. Default: <repo>/.wizard */
  artifactDir?: string;
  /** Minimum trust for a claim to count toward goal satisfaction. Default 0.6. */
  goalTrustThreshold?: number;
}

export interface InvestigationBudget {
  maxNodeExecutions: number;
  executionsUsed: number;
  maxPlannerCalls?: number;
  plannerCallsUsed?: number;
  maxExecutionTimeMs?: number;
}

// ─────────────────────────────────────────────────────────────────────────────
// Investigation Node (lives ONLY in the Investigation Graph)
// ─────────────────────────────────────────────────────────────────────────────

export type InvestigationNodeType =
  | "discovery"
  | "read"
  | "execute"
  | "parse"
  | "verify"
  | "synthesize"
  | "planner"
  | "checkpoint";

export type NodeStatus =
  | "waiting" // exists, dependencies not yet satisfied
  | "ready" // all dependencies satisfied, eligible for execution
  | "blocked" // cannot proceed (missing/failed dependency)
  | "running"
  | "complete"
  | "failed"
  | "skipped";

/** A structured "if the hypothesis holds / fails, record this fact" template. */
export interface ClaimTemplate {
  type: string; // e.g. "RUNTIME_STATUS"
  value: string; // e.g. "verified"
  /**
   * Optional trust hint from the Planner. The Trust Engine treats this as
   * METADATA ONLY — it never becomes the final trust value directly.
   */
  trustWeight?: number;
  /** Optional relationships the claim participates in. */
  relationships?: ClaimRelationshipTemplate[];
}

export interface ClaimRelationshipTemplate {
  type: string; // e.g. "DEPENDS_ON"
  targetClaimType: string; // matched against existing claim types
  targetClaimValue?: string;
}

export type UnexpectedAction = "escalate_to_planner" | "record_only";

export interface NodeError {
  message: string;
  code?: string;
  detail?: string;
}

// ── Node actions (discriminated union) ──────────────────────────────────────

export interface DiscoveryAction {
  type: "discovery";
  pattern: string;
  directory?: string;
}

export interface ReadAction {
  type: "read";
  filePath: string;
}

export interface ExecuteAction {
  type: "execute";
  command: string;
  workingDirectory?: string;
  timeoutMs?: number;
}

export interface ParseAction {
  type: "parse";
  sourceObservationId: ObservationId;
  parser: string; // e.g. "package.json", "requirements.txt", "dockerfile"
}

export interface VerifyAction {
  type: "verify";
  claimId?: ClaimId;
  evidenceIds: ObservationId[];
}

export interface SynthesizeAction {
  type: "synthesize";
  observationIds: ObservationId[];
}

export interface PlannerAction {
  type: "planner";
  reason: string;
}

export interface CheckpointAction {
  type: "checkpoint";
  goalId: GoalId;
}

export type NodeAction =
  | DiscoveryAction
  | ReadAction
  | ExecuteAction
  | ParseAction
  | VerifyAction
  | SynthesizeAction
  | PlannerAction
  | CheckpointAction;

/**
 * The full Investigation Node contract. Every field the architecture requires
 * is present. `nodeId` is unique within an investigation.
 */
export interface InvestigationNode {
  nodeId: NodeId;
  type: InvestigationNodeType;
  action: NodeAction;
  hypothesis: string;
  successClaim?: ClaimTemplate;
  failureClaim?: ClaimTemplate;
  unexpectedAction?: UnexpectedAction;
  parentNodeId?: NodeId;
  dependencies: NodeId[];
  /** goal this node contributes evidence toward (for prioritisation). */
  goalId?: GoalId;
  status: NodeStatus;
  observationId?: ObservationId;
  createdAt: Timestamp;
  completedAt?: Timestamp;
  error?: NodeError;
}

/**
 * What the Planner is allowed to return: a node WITHOUT runtime-owned fields
 * (no status, no timestamps, no observationId). The Runtime materialises this
 * into a real `InvestigationNode`. This type-level separation is the enforcement
 * of "the Planner does not create graph nodes".
 */
export interface PlannerNodeProposal {
  nodeId?: NodeId; // Planner may suggest; Runtime may reassign for uniqueness
  type: InvestigationNodeType;
  action: NodeAction;
  hypothesis: string;
  successClaim?: ClaimTemplate;
  failureClaim?: ClaimTemplate;
  unexpectedAction?: UnexpectedAction;
  parentNodeId?: NodeId;
  dependencies?: NodeId[];
  goalId?: GoalId;
}

export interface PlannerNodeBatch {
  nodes: PlannerNodeProposal[];
  /** free-form note for logs/report; never affects control flow. */
  rationale?: string;
}

// ─────────────────────────────────────────────────────────────────────────────
// Investigation Graph edges
// ─────────────────────────────────────────────────────────────────────────────

export type InvestigationEdgeType = "parent" | "dependency";

export interface InvestigationEdge {
  from: NodeId;
  to: NodeId;
  type: InvestigationEdgeType;
}

// ─────────────────────────────────────────────────────────────────────────────
// Observation (immutable; lives in the Observation Store)
// ─────────────────────────────────────────────────────────────────────────────

export type ObservationType =
  | "file_content"
  | "command_result"
  | "discovery_result"
  | "parse_result"
  | "verify_result"
  | "synthesis_result"
  | "planner_result"
  | "checkpoint_result"
  | "error";

export interface FileContentData {
  filePath: string;
  content: string;
  bytes: number;
  exists: boolean;
}

export interface CommandResultData {
  command: string;
  workingDirectory: string;
  exitCode: number | null;
  stdout: string;
  stderr: string;
  timedOut: boolean;
  durationMs: number;
}

export interface DiscoveryResultData {
  pattern: string;
  matches: string[];
}

export interface ParseResultData {
  parser: string;
  sourceObservationId: ObservationId;
  extracted: Record<string, unknown>;
}

export interface GenericObservationData {
  [key: string]: unknown;
}

export type ObservationData =
  | FileContentData
  | CommandResultData
  | DiscoveryResultData
  | ParseResultData
  | GenericObservationData;

export interface Observation {
  readonly observationId: ObservationId;
  readonly nodeId: NodeId;
  readonly type: ObservationType;
  readonly data: ObservationData;
  readonly createdAt: Timestamp;
  readonly immutable: true;
}

// ─────────────────────────────────────────────────────────────────────────────
// Claim (immutable; lives ONLY in the Knowledge Graph)
// ─────────────────────────────────────────────────────────────────────────────

export interface ClaimProvenance {
  sourceNodeId: NodeId;
  observationId: ObservationId;
  investigationId: InvestigationId;
}

export type EvidencePolarity = "supporting" | "contradicting";

export type EvidenceSourceKind =
  | "execution" // strongest — the code actually ran
  | "structured_file" // package.json / Dockerfile parse
  | "documentation" // README / comments
  | "inference"; // cognitive extraction / derived

export interface Evidence {
  observationId: ObservationId;
  nodeId: NodeId;
  polarity: EvidencePolarity;
  sourceKind: EvidenceSourceKind;
  /** base strength of this evidence before combination, 0..1 */
  weight: number;
  /**
   * The claim VALUE this evidence attests to. Polarity is derived from this
   * relative to the claim's current winning value, so trust can be recomputed
   * deterministically whenever new evidence arrives.
   */
  attestedValue?: string;
  note?: string;
}

export interface Claim {
  readonly claimId: ClaimId;
  readonly type: string; // e.g. "RUNTIME_STATUS"
  value: string; // current best value
  /** computed by the Trust Engine only, 0..1 */
  trust: number;
  /** lifecycle status of the claim, derived from evidence + trust. */
  status: ClaimStatus;
  evidence: Evidence[];
  /**
   * Provenance entries — one per contributing observation. The FIRST entry is
   * the originating node/observation; more are appended as corroborating
   * evidence arrives.
   */
  provenance: ClaimProvenance;
  provenanceHistory: ClaimProvenance[];
  readonly createdAt: Timestamp;
  updatedAt: Timestamp;
}

export type ClaimStatus =
  | "asserted" // has supporting evidence
  | "contested" // both supporting and contradicting evidence
  | "refuted"; // net-contradicted

export type ClaimRelationshipType = KnowledgeRelationshipType;

/** Edge in the Knowledge Graph, addressed by claim id. */
export interface ClaimRelationship {
  relationshipId: RelationshipId;
  type: ClaimRelationshipType;
  from: ClaimId;
  to: ClaimId;
}

export type KnowledgeRelationshipType =
  | "DEPENDS_ON"
  | "USES"
  | "CONTAINS"
  | "RUNS_ON"
  | "CONFIGURES"
  | "RELATED_TO";

// ─────────────────────────────────────────────────────────────────────────────
// Goals & checkpoints
// ─────────────────────────────────────────────────────────────────────────────

export type GoalStatus = "waiting" | "in_progress" | "satisfied" | "unsatisfiable";

/** A single required-claim condition for satisfying a goal. */
export interface GoalRequirement {
  claimType: string;
  /** if set, the claim's value must equal this. */
  expectedValue?: string;
  /** if set, the claim's value must NOT equal this (e.g. not "broken"). */
  notValue?: string;
  minTrust?: number;
  description: string;
}

export interface Goal {
  goalId: GoalId;
  name: string; // e.g. "Verify Runtime"
  technology: string; // e.g. "Node.js"
  status: GoalStatus;
  requirements: GoalRequirement[];
  checkpointNodeId?: NodeId;
}

// ─────────────────────────────────────────────────────────────────────────────
// Technology Plan (initial Planner output)
// ─────────────────────────────────────────────────────────────────────────────

export interface TechnologyPlanItem {
  name: string;
  confidence: Confidence;
  signals: string[];
  initialGoals: string[];
  priorityFiles: string[];
}

export interface TechnologyPlan {
  technologies: TechnologyPlanItem[];
}

// ─────────────────────────────────────────────────────────────────────────────
// Hypothesis evaluation
// ─────────────────────────────────────────────────────────────────────────────

export type EvaluationOutcome = "SUCCESS" | "FAILURE" | "UNEXPECTED";

export interface EvaluationResult {
  outcome: EvaluationOutcome;
  reason: string;
  /** the claim template selected (success/failure) if deterministic. */
  claimTemplate?: ClaimTemplate;
}

// ─────────────────────────────────────────────────────────────────────────────
// Planner context (progressive, compact)
// ─────────────────────────────────────────────────────────────────────────────

export interface GoalSummary {
  goalId: GoalId;
  name: string;
  technology: string;
  status: GoalStatus;
  requirements: string[]; // human-readable requirement descriptions
}

export interface RelevantClaimSummary {
  type: string;
  value: string;
  trust: number;
}

export interface RelevantKnowledgeSummary {
  claims: RelevantClaimSummary[];
}

export interface InvestigationNodeSummary {
  nodeId: NodeId;
  type: InvestigationNodeType;
  action: string; // compact string form
  hypothesis: string;
  status: NodeStatus;
  outcome?: EvaluationOutcome;
}

export interface OpenQuestion {
  question: string;
  missingClaimType: string;
}

export interface ObservationSummary {
  observationId: ObservationId;
  type: ObservationType;
  summary: string; // compact, truncated
}

export interface IncrementalRepositoryContext {
  repositoryName: string;
  keyFiles: string[];
  /** file path -> short excerpt of already-read content. */
  readFiles: Record<string, string>;
}

export interface BudgetSummary {
  nodeExecutionsRemaining: number;
  plannerCallsRemaining: number | null;
}

export interface PlannerContext {
  investigationId: InvestigationId;
  userIntent: UserIntent;
  currentGoal: GoalSummary;
  knowledgeGraph: RelevantKnowledgeSummary;
  recentInvestigationNodes: InvestigationNodeSummary[];
  openQuestions: OpenQuestion[];
  repositoryContext: IncrementalRepositoryContext;
  recentObservations: ObservationSummary[];
  budget: BudgetSummary;
}

/** Context passed to the escalation planner when a result is UNEXPECTED. */
export interface EscalationContext {
  investigationId: InvestigationId;
  node: InvestigationNodeSummary;
  hypothesis: string;
  observation: ObservationSummary;
  currentGoal: GoalSummary;
  budget: BudgetSummary;
}

// ─────────────────────────────────────────────────────────────────────────────
// Final result
// ─────────────────────────────────────────────────────────────────────────────

export interface InvestigationStatistics {
  nodesExecuted: number;
  plannerCalls: number;
  claimsCreated: number;
  observationsCreated: number;
  goalsSatisfied: number;
  goalsTotal: number;
}

export interface InvestigationGraphSnapshot {
  nodes: InvestigationNode[];
  edges: InvestigationEdge[];
}

export interface KnowledgeGraphSnapshot {
  claims: Claim[];
  relationships: ClaimRelationship[];
}

export interface InvestigationResult {
  investigationId: InvestigationId;
  state: InvestigationState;
  technologyPlan: TechnologyPlan | null;
  investigationGraph: InvestigationGraphSnapshot;
  knowledgeGraph: KnowledgeGraphSnapshot;
  observations: Observation[];
  claims: Claim[];
  goals: Goal[];
  reportPath?: string;
  reportMarkdown?: string;
  statistics: InvestigationStatistics;
  terminationReason: string;
}
