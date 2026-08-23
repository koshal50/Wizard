/**
 * TrustEngine — computes a Claim's trust score and status from its Evidence,
 * DETERMINISTICALLY and with no LLM.
 *
 * Model:
 *   - Each piece of evidence attests a value with a base weight (from its source
 *     kind: execution > structured_file > documentation > inference).
 *   - Independent evidence for the SAME value combines by noisy-OR:
 *       combined = 1 - Π(1 - wᵢ)
 *     so corroboration raises confidence toward (but never past) 1.
 *   - Evidence attesting a DIFFERENT value is contradiction.
 *   - trust = support × (1 − contradiction), clamped to [0, 1].
 *
 * SECURITY / ARCHITECTURE: the Planner may attach a `trustWeight` hint to a claim
 * template. This engine IGNORES it for the final score — trust is earned from
 * real evidence, never asserted by the Planner. (§ "Do not allow Planner output
 * to directly set final trust.")
 */
import type { Claim, ClaimStatus, Evidence } from "../core/types.ts";

export interface TrustResult {
  trust: number;
  status: ClaimStatus;
  supportScore: number;
  contradictScore: number;
}

function noisyOr(weights: number[]): number {
  let product = 1;
  for (const w of weights) product *= 1 - clamp01(w);
  return 1 - product;
}

function clamp01(n: number): number {
  if (Number.isNaN(n)) return 0;
  return Math.max(0, Math.min(1, n));
}

/**
 * Compute trust for a claim whose stated value is `claimValue`, given evidence.
 * Evidence with no `attestedValue` is treated as supporting the claim value
 * (it was recorded specifically for this claim).
 */
export function computeTrust(claimValue: string, evidence: Evidence[]): TrustResult {
  const supporting: number[] = [];
  const contradicting: number[] = [];

  for (const e of evidence) {
    const attests = e.attestedValue ?? claimValue;
    if (attests === claimValue) supporting.push(e.weight);
    else contradicting.push(e.weight);
  }

  const supportScore = noisyOr(supporting);
  const contradictScore = noisyOr(contradicting);
  const trust = clamp01(supportScore * (1 - contradictScore));

  let status: ClaimStatus;
  if (contradicting.length === 0) status = "asserted";
  else if (supportScore >= contradictScore) status = "contested";
  else status = "refuted";

  return { trust, status, supportScore, contradictScore };
}

/** Apply a freshly computed trust result to a claim (returns a new object). */
export function applyTrust(claim: Claim, result: TrustResult, updatedAt: string): Claim {
  return { ...claim, trust: result.trust, status: result.status, updatedAt };
}
