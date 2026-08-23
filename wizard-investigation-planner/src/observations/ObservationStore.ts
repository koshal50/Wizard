/**
 * Observation Store — append-only, immutable record of what actually happened
 * when a node executed. Observations are frozen on insert; there is no update or
 * delete API. Every executed node produces exactly one Observation.
 */
import type { NodeId, Observation, ObservationId } from "../core/types.ts";

export class ObservationStore {
  private readonly byId = new Map<ObservationId, Observation>();
  private readonly byNode = new Map<NodeId, ObservationId>();

  add(observation: Observation): Observation {
    if (this.byId.has(observation.observationId)) {
      throw new Error(`Duplicate observation id: ${observation.observationId}`);
    }
    const frozen = Object.freeze({ ...observation }) as Observation;
    this.byId.set(frozen.observationId, frozen);
    this.byNode.set(frozen.nodeId, frozen.observationId);
    return frozen;
  }

  get(id: ObservationId): Observation | undefined {
    return this.byId.get(id);
  }

  forNode(nodeId: NodeId): Observation | undefined {
    const id = this.byNode.get(nodeId);
    return id ? this.byId.get(id) : undefined;
  }

  all(): Observation[] {
    return Array.from(this.byId.values());
  }

  size(): number {
    return this.byId.size;
  }
}
