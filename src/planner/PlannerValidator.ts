/**
 * PlannerValidator — the semantic security gate for Planner output.
 *
 * The schema layer (`schemas.ts`) guarantees SHAPE. This layer guarantees
 * SAFETY + CONSISTENCY on top of that:
 *
 *   1. `node.type` must match `node.action.type` (a "read" node must carry a
 *      read action, etc.). Mismatches are how a confused/hostile model could try
 *      to get an execute action past a "harmless read" label.
 *   2. Every READ file path must resolve INSIDE the repository (no `..`/absolute
 *      escape).
 *   3. Every EXECUTE command must pass the command allowlist + dangerous-pattern
 *      check, and its working directory must stay inside the repo.
 *   4. The batch must not exceed the remaining node budget.
 *
 * Invalid proposals are DROPPED (not silently mutated) and the reason recorded,
 * so a partially-bad batch still yields the safe subset instead of aborting.
 */
import type { PlannerNodeBatch, PlannerNodeProposal } from "../core/types.ts";
import { checkCommandSafety, resolveInsideRepo } from "../util/safety.ts";
import { safeParse } from "../validation/schema.ts";
import { plannerNodeBatchSchema, technologyPlanSchema } from "./schemas.ts";
import type { TechnologyPlan } from "../core/types.ts";

export interface ValidationOptions {
  repoRoot: string;
  /** remaining node executions; batch is truncated to this. */
  budgetRemaining: number;
  allowExecution: boolean;
}

export interface RejectedProposal {
  proposal: PlannerNodeProposal;
  reason: string;
}

export interface ValidatedBatch {
  accepted: PlannerNodeProposal[];
  rejected: RejectedProposal[];
  rationale?: string;
}

/** Validate a single proposal's semantics + security. Returns null reason if OK. */
export function validateProposal(
  proposal: PlannerNodeProposal,
  opts: ValidationOptions,
): string | null {
  if (proposal.type !== proposal.action.type) {
    return `node type "${proposal.type}" does not match action type "${proposal.action.type}"`;
  }

  const action = proposal.action;
  if (action.type === "read") {
    const safe = resolveInsideRepo(opts.repoRoot, action.filePath);
    if (!safe.ok) return `unsafe read path: ${safe.reason}`;
  }

  if (action.type === "execute") {
    if (!opts.allowExecution) {
      return "execute proposals rejected: execution disabled for this investigation";
    }
    const cmd = checkCommandSafety(action.command);
    if (!cmd.ok) return `unsafe command: ${cmd.reason}`;
    if (action.workingDirectory) {
      const wd = resolveInsideRepo(opts.repoRoot, action.workingDirectory);
      if (!wd.ok) return `unsafe working directory: ${wd.reason}`;
    }
  }

  if (action.type === "discovery" && action.directory) {
    const safe = resolveInsideRepo(opts.repoRoot, action.directory);
    if (!safe.ok) return `unsafe discovery directory: ${safe.reason}`;
  }

  return null;
}

/**
 * Validate a *raw* (unparsed) batch object from a provider: schema first, then
 * semantics/security, then budget truncation.
 */
export function validateBatch(raw: unknown, opts: ValidationOptions): ValidatedBatch {
  const parsed = safeParse(plannerNodeBatchSchema, raw);
  if (!parsed.ok) {
    return { accepted: [], rejected: [], rationale: `batch failed schema: ${parsed.errors.join("; ")}` };
  }
  return validateParsedBatch(parsed.value, opts);
}

/** Validate an already schema-valid batch (semantics/security/budget only). */
export function validateParsedBatch(batch: PlannerNodeBatch, opts: ValidationOptions): ValidatedBatch {
  const accepted: PlannerNodeProposal[] = [];
  const rejected: RejectedProposal[] = [];

  for (const proposal of batch.nodes) {
    if (accepted.length >= opts.budgetRemaining) {
      rejected.push({ proposal, reason: "exceeds remaining node budget" });
      continue;
    }
    const reason = validateProposal(proposal, opts);
    if (reason) rejected.push({ proposal, reason });
    else accepted.push(proposal);
  }

  return { accepted, rejected, rationale: batch.rationale };
}

export interface ValidatedTechnologyPlan {
  ok: boolean;
  plan?: TechnologyPlan;
  errors?: string[];
}

export function validateTechnologyPlan(raw: unknown): ValidatedTechnologyPlan {
  const parsed = safeParse(technologyPlanSchema, raw);
  if (!parsed.ok) return { ok: false, errors: parsed.errors };
  return { ok: true, plan: parsed.value };
}
