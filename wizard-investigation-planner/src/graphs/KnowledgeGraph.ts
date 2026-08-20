/**
 * Knowledge Graph — GRAPH 1 of the two-graph architecture.
 *
 * Answers: "WHAT do we know?" It stores Claims and typed relationships between
 * them. It starts empty and grows only as evidence is validated. It NEVER
 * stores Investigation Nodes.
 *
 * The Planner CANNOT write here directly — only the Runtime (via the Claim /
 * Evidence / Trust pipeline) calls `upsertClaim`. Every claim carries provenance
 * back to the Investigation Node + Observation that produced it.
 */
import type {
  Claim,
  ClaimId,
  ClaimRelationship,
  KnowledgeGraphSnapshot,
} from "../core/types.ts";

export class KnowledgeGraph {
  private readonly claims = new Map<ClaimId, Claim>();
  /** index of claims by type so we can find "the runtime status claim" quickly. */
  private readonly byType = new Map<string, Set<ClaimId>>();
  private readonly relationships: ClaimRelationship[] = [];

  upsertClaim(claim: Claim): void {
    if (!this.claims.has(claim.claimId)) {
      const set = this.byType.get(claim.type) ?? new Set<ClaimId>();
      set.add(claim.claimId);
      this.byType.set(claim.type, set);
    }
    this.claims.set(claim.claimId, claim);
  }

  getClaim(claimId: ClaimId): Claim | undefined {
    return this.claims.get(claimId);
  }

  claimsOfType(type: string): Claim[] {
    const ids = this.byType.get(type);
    if (!ids) return [];
    return Array.from(ids)
      .map((id) => this.claims.get(id)!)
      .filter(Boolean);
  }

  allClaims(): Claim[] {
    return Array.from(this.claims.values());
  }

  addRelationship(rel: ClaimRelationship): void {
    const exists = this.relationships.some(
      (r) => r.from === rel.from && r.to === rel.to && r.type === rel.type,
    );
    if (!exists) this.relationships.push(rel);
  }

  allRelationships(): ClaimRelationship[] {
    return this.relationships.slice();
  }

  /** Related claims (either direction) — used to build compact Planner context. */
  relatedClaims(claimId: ClaimId): Claim[] {
    const related = new Set<ClaimId>();
    for (const r of this.relationships) {
      if (r.from === claimId) related.add(r.to);
      if (r.to === claimId) related.add(r.from);
    }
    return Array.from(related)
      .map((id) => this.claims.get(id)!)
      .filter(Boolean);
  }

  snapshot(): KnowledgeGraphSnapshot {
    return { claims: this.allClaims(), relationships: this.allRelationships() };
  }

  size(): number {
    return this.claims.size;
  }

  render(): string {
    const lines: string[] = [];
    lines.push("Claims:");
    for (const c of this.allClaims()) {
      lines.push(
        `  [${c.claimId}] ${c.type} = ${c.value}  (trust=${c.trust.toFixed(2)}, status=${c.status})`,
      );
      lines.push(
        `      via ${c.provenance.sourceNodeId} / ${c.provenance.observationId}`,
      );
    }
    if (this.relationships.length) {
      lines.push("Relationships:");
      for (const r of this.relationships) {
        lines.push(`  ${r.from} ${r.type} ${r.to}`);
      }
    }
    return lines.join("\n");
  }
}
