/**
 * Evidence extractors — deterministic, no-LLM mapping from an Observation to the
 * kind and base strength of evidence it constitutes.
 *
 * The ordering of `EvidenceSourceKind` strength is the heart of the trust model:
 * something the code ACTUALLY DID (execution) outranks a parsed config file,
 * which outranks documentation prose, which outranks a mere inference. The Trust
 * Engine combines these weights; the extractor only classifies.
 */
import type { Evidence, EvidenceSourceKind, Observation } from "../core/types.ts";

const SOURCE_WEIGHT: Record<EvidenceSourceKind, number> = {
  execution: 0.9,
  structured_file: 0.7,
  documentation: 0.4,
  inference: 0.25,
};

export function weightForSourceKind(kind: EvidenceSourceKind): number {
  return SOURCE_WEIGHT[kind];
}

/** Classify what kind of evidence an observation represents. */
export function sourceKindForObservation(observation: Observation): EvidenceSourceKind {
  switch (observation.type) {
    case "command_result":
      return "execution";
    case "parse_result":
      return "structured_file";
    case "file_content": {
      const d = observation.data as { filePath?: string };
      const path = (d.filePath ?? "").toLowerCase();
      if (path.endsWith(".md") || path.includes("readme")) return "documentation";
      return "structured_file";
    }
    case "discovery_result":
    case "synthesis_result":
    case "verify_result":
    case "planner_result":
    case "checkpoint_result":
    case "error":
    default:
      return "inference";
  }
}

/**
 * Build a single Evidence entry attesting `attestedValue`. Polarity is filled in
 * later by the EvidenceEngine (it depends on the claim's winning value), so it
 * defaults to "supporting" here.
 */
export function buildEvidence(
  observation: Observation,
  attestedValue: string,
  note?: string,
): Evidence {
  const sourceKind = sourceKindForObservation(observation);
  return {
    observationId: observation.observationId,
    nodeId: observation.nodeId,
    polarity: "supporting",
    sourceKind,
    weight: weightForSourceKind(sourceKind),
    attestedValue,
    note,
  };
}
