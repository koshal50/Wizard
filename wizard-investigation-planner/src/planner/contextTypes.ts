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
