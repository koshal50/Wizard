/**
 * GoalEngine — evaluates GOAL satisfaction from the Knowledge Graph.
 *
 * A goal is satisfied when every one of its `GoalRequirement`s is met by a claim:
 * the claim exists, its value matches (`expectedValue`) / avoids (`notValue`) as
 * required, and its trust clears the requirement's `minTrust` (falling back to a
 * configured default threshold).
 *
 * The GoalEngine is READ-ONLY over claims — it derives status, it never creates
 * claims or sets trust. It is also the component that decides CONVERGENCE:
 * whether all goals are resolved (satisfied or provably unsatisfiable).
 */
import type { Goal, GoalRequirement, GoalStatus } from "../core/types.ts";
import type { ClaimStore } from "../claims/ClaimStore.ts";

export interface GoalEvaluation {
  goalId: string;
  status: GoalStatus;
  satisfiedClaimTypes: string[];
  missingClaimTypes: string[];
  rationale: string;
}

export interface GoalEngineOptions {
  defaultTrustThreshold: number;
}

export class GoalEngine {
  private readonly claims: ClaimStore;
  private readonly defaultTrust: number;

  constructor(claims: ClaimStore, opts: GoalEngineOptions) {
    this.claims = claims;
    this.defaultTrust = opts.defaultTrustThreshold;
  }

  evaluate(goal: Goal): GoalEvaluation {
    const satisfied: string[] = [];
    const missing: string[] = [];

    for (const req of goal.requirements) {
      if (this.requirementMet(req)) satisfied.push(req.claimType);
      else missing.push(req.claimType);
    }

    const status: GoalStatus = missing.length === 0 ? "satisfied" : goal.status === "waiting" ? "waiting" : "in_progress";
    const rationale =
      missing.length === 0
        ? `all ${satisfied.length} requirement(s) satisfied`
        : `${missing.length} requirement(s) unmet: ${missing.join(", ")}`;

    return { goalId: goal.goalId, status, satisfiedClaimTypes: satisfied, missingClaimTypes: missing, rationale };
  }

  private requirementMet(req: GoalRequirement): boolean {
    const claim = this.claims.findByType(req.claimType);
    if (!claim) return false;
    if (req.expectedValue !== undefined && claim.value !== req.expectedValue) return false;
    if (req.notValue !== undefined && claim.value === req.notValue) return false;
    const minTrust = req.minTrust ?? this.defaultTrust;
    if (claim.trust < minTrust) return false;
    // A refuted claim never satisfies a requirement.
    if (claim.status === "refuted") return false;
    return true;
  }
}
