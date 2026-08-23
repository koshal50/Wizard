/**
 * EvidenceEngine — the ONLY component that writes Claims to the Knowledge Graph.
 *
 * When a node completes and the evaluator selects a claim template (success or
 * failure), the Runtime calls `recordClaim`. The engine:
 *   1. Builds an Evidence entry from the producing Observation (deterministic
 *      source-kind + weight).
 *   2. Finds the existing canonical claim of that type, or creates a new one.
 *   3. Appends the evidence, recomputes trust via the TrustEngine, updates the
 *      claim value to the currently best-supported value, and appends provenance.
 *   4. Writes the result to BOTH the ClaimStore (identity) and the KnowledgeGraph
 *      (queryable view), and materialises any relationship templates as edges.
 *
 * The Planner's `trustWeight` hint on the template is recorded as evidence
 * metadata only — it never becomes the trust score (TrustEngine ignores it).
 */
import type {
  Claim,
  ClaimProvenance,
  ClaimRelationship,
  ClaimTemplate,
  Evidence,
  InvestigationId,
  Observation,
} from "../core/types.ts";
import type { ClaimStore } from "../claims/ClaimStore.ts";
import type { KnowledgeGraph } from "../graphs/KnowledgeGraph.ts";
import type { Clock } from "../util/clock.ts";
import type { IdFactory } from "../util/ids.ts";
import type { Logger } from "../util/logger.ts";
import { buildEvidence } from "./extractors.ts";
import { computeTrust } from "../trust/TrustEngine.ts";

export interface EvidenceEngineDeps {
  claims: ClaimStore;
  knowledge: KnowledgeGraph;
  ids: IdFactory;
  clock: Clock;
  logger: Logger;
  investigationId: InvestigationId;
}

export class EvidenceEngine {
  private readonly deps: EvidenceEngineDeps;

  constructor(deps: EvidenceEngineDeps) {
    this.deps = deps;
  }

  /**
   * Record the claim implied by `template`, backed by `observation`, produced by
   * node `sourceNodeId`. Returns the updated/created claim.
   */
  recordClaim(template: ClaimTemplate, observation: Observation, sourceNodeId: string): Claim {
    const { claims, knowledge, ids, clock } = this.deps;
    const now = clock.now();

    const evidence = buildEvidence(observation, template.value, this.trustHintNote(template));
    const provenance: ClaimProvenance = {
      sourceNodeId,
      observationId: observation.observationId,
      investigationId: this.deps.investigationId,
    };

    const existing = claims.findByType(template.type);
    const merged: Claim = existing
      ? this.mergeEvidence(existing, evidence, provenance, now)
      : this.createClaim(template, evidence, provenance, now, ids);

    // Recompute value + trust from the full evidence set (deterministic).
    const bestValue = this.bestSupportedValue(merged.evidence, template.value);
    const trust = computeTrust(bestValue, merged.evidence);
    // Refresh polarities relative to the winning value.
    const evidenceWithPolarity = merged.evidence.map((e) => ({
      ...e,
      polarity: (e.attestedValue ?? bestValue) === bestValue ? ("supporting" as const) : ("contradicting" as const),
    }));

    const finalClaim: Claim = {
      ...merged,
      value: bestValue,
      evidence: evidenceWithPolarity,
      trust: trust.trust,
      status: trust.status,
      updatedAt: now,
    };

    claims.put(finalClaim);
    knowledge.upsertClaim(finalClaim);
    this.materializeRelationships(finalClaim, template);

    this.deps.logger.info("evidence.claim.recorded", {
      claimId: finalClaim.claimId,
      type: finalClaim.type,
      value: finalClaim.value,
      trust: Number(finalClaim.trust.toFixed(3)),
      status: finalClaim.status,
      evidenceCount: finalClaim.evidence.length,
    });
    return finalClaim;
  }

  private createClaim(
    template: ClaimTemplate,
    evidence: Evidence,
    provenance: ClaimProvenance,
    now: string,
    ids: IdFactory,
  ): Claim {
    return {
      claimId: ids.next("claim"),
      type: template.type,
      value: template.value,
      trust: 0,
      status: "asserted",
      evidence: [evidence],
      provenance,
      provenanceHistory: [provenance],
      createdAt: now,
      updatedAt: now,
    };
  }

  private mergeEvidence(
    existing: Claim,
    evidence: Evidence,
    provenance: ClaimProvenance,
    now: string,
  ): Claim {
    // Idempotency: do not double-count the same observation.
    const already = existing.evidence.some((e) => e.observationId === evidence.observationId);
    const evidenceList = already ? existing.evidence : [...existing.evidence, evidence];
    const provHistory = already
      ? existing.provenanceHistory
      : [...existing.provenanceHistory, provenance];
    return { ...existing, evidence: evidenceList, provenanceHistory: provHistory, updatedAt: now };
  }

  /** The value with the greatest combined supporting weight wins ties toward `preferred`. */
  private bestSupportedValue(evidence: Evidence[], preferred: string): string {
    const totals = new Map<string, number>();
    for (const e of evidence) {
      const v = e.attestedValue ?? preferred;
      totals.set(v, (totals.get(v) ?? 0) + e.weight);
    }
    let best = preferred;
    let bestWeight = totals.get(preferred) ?? -1;
    for (const [value, weight] of totals) {
      if (weight > bestWeight) {
        best = value;
        bestWeight = weight;
      }
    }
    return best;
  }

  private materializeRelationships(claim: Claim, template: ClaimTemplate): void {
    if (!template.relationships?.length) return;
    const { knowledge, ids } = this.deps;
    for (const rel of template.relationships) {
      const targets = knowledge.claimsOfType(rel.targetClaimType).filter((t) =>
        rel.targetClaimValue === undefined ? true : t.value === rel.targetClaimValue,
      );
      for (const target of targets) {
        const relationship: ClaimRelationship = {
          relationshipId: ids.next("rel"),
          type: normalizeRelType(rel.type),
          from: claim.claimId,
          to: target.claimId,
        };
        knowledge.addRelationship(relationship);
      }
    }
  }

  private trustHintNote(template: ClaimTemplate): string | undefined {
    return template.trustWeight === undefined
      ? undefined
      : `planner trust hint ${template.trustWeight} (metadata only; ignored by TrustEngine)`;
  }
}

const KNOWN_REL_TYPES = ["DEPENDS_ON", "USES", "CONTAINS", "RUNS_ON", "CONFIGURES", "RELATED_TO"] as const;
type KnownRel = (typeof KNOWN_REL_TYPES)[number];

function normalizeRelType(t: string): KnownRel {
  const upper = t.toUpperCase();
  return (KNOWN_REL_TYPES as readonly string[]).includes(upper) ? (upper as KnownRel) : "RELATED_TO";
}
