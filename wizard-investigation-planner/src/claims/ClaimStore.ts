/**
 * Claim Store — the durable record of every Claim, keyed by id and by type.
 *
 * The Knowledge Graph is the queryable view; the ClaimStore is the owner of
 * Claim identity and the place the Runtime looks up "is there already a claim of
 * type X?" before creating a new one (so corroborating evidence merges into one
 * claim rather than duplicating).
 */
import type { Claim, ClaimId } from "../core/types.ts";

export class ClaimStore {
  private readonly byId = new Map<ClaimId, Claim>();
  private readonly idByType = new Map<string, ClaimId>();

  put(claim: Claim): void {
    this.byId.set(claim.claimId, claim);
    this.idByType.set(claim.type, claim.claimId);
  }

  get(id: ClaimId): Claim | undefined {
    return this.byId.get(id);
  }

  /** the single canonical claim for a type, if one exists. */
  findByType(type: string): Claim | undefined {
    const id = this.idByType.get(type);
    return id ? this.byId.get(id) : undefined;
  }

  all(): Claim[] {
    return Array.from(this.byId.values());
  }

  size(): number {
    return this.byId.size;
  }
}
