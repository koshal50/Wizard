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
  /** Every file the scan saw, so a named target can be resolved to real paths. */
  treeFiles: string[];
  /**
   * The command family: "investigate" | "verify" | "explain" | "report".
   *
   * Not the user's words. This field was documented as "the question the user
   * asked" and has never held one — the Runtime's request contract types it as
   * that literal union. The question is `question` below; conflating the two is
   * what made `explain` a subject to go and read.
   */
  intent: string;
  /** The question the user asked, verbatim. Empty when they typed none. */
  question: string;
  /** The things the user named, verbatim. */
  targets: string[];
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
