/**
 * Planner-local context helper types.
 *
 * `ManifestSummary` is the subset of the Repository Manifest the deterministic
 * heuristic provider reads to derive a Technology Plan. It is intentionally a
 * plain data bag (arrays of strings) so it round-trips cleanly through the
 * provider's structured `context` channel.
 */
export interface ManifestSummary {
  languages: string[];
  frameworks: string[];
  packageManagers: string[];
  dependencies: string[];
  databases: string[];
  keyFiles: string[];
  entryFiles: string[];
  projectType: string;
}

import type { PlannerContext } from "../core/types.ts";

/**
 * The two artifacts the ongoing planner consumes: the human/LLM-readable
 * `plannerContext` (rendered into the prompt) and the structured
 * `heuristicContext` the offline provider reads to decide deterministically.
 *
 * The Runtime's Context Engine now owns building the projection this is derived
 * from; the Planner only consumes the safe packet (see src/http/server.ts),
 * which is why this type no longer lives in a Planner-side context builder.
 */
export interface BuiltContext {
  plannerContext: PlannerContext;
  heuristicContext: Record<string, unknown>;
}
