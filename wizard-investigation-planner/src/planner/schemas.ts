/**
 * Validation schemas for PLANNER OUTPUT.
 *
 * Everything a provider returns is untrusted. These schemas are the type-safe
 * gate: the Planner never hands the Runtime anything that has not passed them.
 *
 * Note the deliberate use of `object(..., { allowUnknownKeys: false })` (the
 * default): if the model tries to smuggle runtime-owned fields (`status`,
 * `createdAt`, `observationId`, `trust`, ...) into a proposal, validation
 * REJECTS it. That is the schema-level enforcement of "the Planner cannot set
 * runtime-owned fields".
 */
import {
  array,
  enum_,
  number,
  object,
  string,
  taggedUnion,
} from "../validation/schema.ts";
import type { Schema } from "../validation/schema.ts";
import type {
  ClaimTemplate,
  NodeAction,
  PlannerNodeBatch,
  PlannerNodeProposal,
  TechnologyPlan,
} from "../core/types.ts";

// ── Node actions (discriminated on `type`) ───────────────────────────────────

const discoveryAction = object({
  type: enum_(["discovery"] as const),
  pattern: string({ minLength: 1 }),
  directory: string().optional(),
});

const readAction = object({
  type: enum_(["read"] as const),
  filePath: string({ minLength: 1 }),
});

const executeAction = object({
  type: enum_(["execute"] as const),
  command: string({ minLength: 1 }),
  workingDirectory: string().optional(),
  timeoutMs: number({ int: true, min: 0 }).optional(),
});

const parseAction = object({
  type: enum_(["parse"] as const),
  sourceObservationId: string({ minLength: 1 }),
  parser: string({ minLength: 1 }),
});

const verifyAction = object({
  type: enum_(["verify"] as const),
  claimId: string().optional(),
  evidenceIds: array(string()),
});

const synthesizeAction = object({
  type: enum_(["synthesize"] as const),
  observationIds: array(string()),
});

const plannerAction = object({
  type: enum_(["planner"] as const),
  reason: string({ minLength: 1 }),
});

const checkpointAction = object({
  type: enum_(["checkpoint"] as const),
  goalId: string({ minLength: 1 }),
});

const browserAction = object({
  type: enum_(["browser"] as const),
  tool: enum_(["navigate", "snapshot", "extract", "back", "click", "type"] as const),
  url: string({ minLength: 1 }).optional(),
  selector: string({ minLength: 1 }).optional(),
  text: string().optional(),
});

export const nodeActionSchema: Schema<NodeAction> = taggedUnion<NodeAction>("type", {
  discovery: discoveryAction,
  read: readAction,
  execute: executeAction,
  parse: parseAction,
  verify: verifyAction,
  browser: browserAction,
  synthesize: synthesizeAction,
  planner: plannerAction,
  checkpoint: checkpointAction,
});

// ── Claim template ────────────────────────────────────────────────────────────

const claimRelationshipTemplate = object({
  type: string({ minLength: 1 }),
  targetClaimType: string({ minLength: 1 }),
  targetClaimValue: string().optional(),
});

export const claimTemplateSchema: Schema<ClaimTemplate> = object({
  type: string({ minLength: 1 }),
  value: string({ minLength: 1 }),
  trustWeight: number({ min: 0, max: 1 }).optional(),
  relationships: array(claimRelationshipTemplate).optional(),
});

// ── Node proposal + batch ─────────────────────────────────────────────────────

const nodeTypeSchema = enum_([
  "discovery",
  "read",
  "execute",
  "parse",
  "verify",
  "browser",
  "synthesize",
  "planner",
  "checkpoint",
] as const);

const unexpectedActionSchema = enum_(["escalate_to_planner", "record_only"] as const);

export const plannerNodeProposalSchema: Schema<PlannerNodeProposal> = object({
  nodeId: string().optional(),
  type: nodeTypeSchema,
  action: nodeActionSchema,
  hypothesis: string({ minLength: 1 }),
  successClaim: claimTemplateSchema.optional(),
  failureClaim: claimTemplateSchema.optional(),
  unexpectedAction: unexpectedActionSchema.optional(),
  parentNodeId: string().optional(),
  dependencies: array(string()).optional(),
  goalId: string().optional(),
});

export const plannerNodeBatchSchema: Schema<PlannerNodeBatch> = object({
  nodes: array(plannerNodeProposalSchema),
  rationale: string().optional(),
});

// ── Technology plan ─────────────────────────────────────────────────────────

const technologyPlanItemSchema = object({
  name: string({ minLength: 1 }),
  confidence: enum_(["high", "medium", "low"] as const),
  signals: array(string()),
  initialGoals: array(string()),
  priorityFiles: array(string()),
});

export const technologyPlanSchema: Schema<TechnologyPlan> = object({
  technologies: array(technologyPlanItemSchema),
});
