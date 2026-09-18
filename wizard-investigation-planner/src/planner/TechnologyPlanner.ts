/**
 * TechnologyPlanner — produces the INITIAL plan from the Tier-1 manifest only.
 *
 * It asks the provider "what technologies are here and what should we verify
 * first?" and returns a validated `TechnologyPlan`. It never reads files or
 * touches a graph. On any provider/validation failure it returns an empty plan
 * (the Runtime treats that as "nothing to investigate" rather than crashing).
 */
import type { RepositoryManifest } from "../manifest/types.ts";
import { renderManifestForPrompt } from "../manifest/manifest.ts";
import type { TechnologyPlan } from "../core/types.ts";
import type { LLMProvider } from "../llm/LLMProvider.ts";
import type { Logger } from "../util/logger.ts";
import { buildTechnologyPlanPrompt } from "./prompts.ts";
import type { ManifestSummary } from "./contextTypes.ts";
import { technologyPlanSchema } from "./schemas.ts";

export function toManifestSummary(
  manifest: RepositoryManifest,
  intent = "",
  targets: string[] = [],
  question = "",
): ManifestSummary {
  return {
    languages: manifest.languages,
    frameworks: manifest.frameworks,
    packageManagers: manifest.packageManagers,
    dependencies: manifest.dependencies,
    databases: manifest.databases,
    keyFiles: manifest.keyFiles.map((k) => k.path),
    entryFiles: manifest.entryFiles,
    projectType: manifest.projectType,
    treeFiles: manifest.treeFiles,
    intent,
    question,
    targets,
  };
}

export class TechnologyPlanner {
  private readonly llm: LLMProvider;
  private readonly logger: Logger;

  constructor(llm: LLMProvider, logger: Logger) {
    this.llm = llm;
    this.logger = logger;
  }

  /**
   * The INITIAL plan: which technologies are here, and what to verify first.
   *
   * `intent` and `targets` and `question` are everything that differs between
   * two investigations of the same repository. The manifest says what the repo
   * *is*; the intent says which command was run, the targets say what the
   * command was aimed at, and the question is what the user typed when they
   * typed anything. Dropping them — which is what this method used to do, since
   * it took only the manifest — made the plan a pure function of the
   * repository, so asking for the auth flow and asking for the test suite
   * produced byte-for-byte identical plans, goals, nodes and commands.
   */
  async plan(
    manifest: RepositoryManifest,
    intent = "",
    targets: string[] = [],
    question = "",
  ): Promise<TechnologyPlan> {
    const summary = toManifestSummary(manifest, intent, targets, question);
    const request = buildTechnologyPlanPrompt(renderManifestForPrompt(manifest), summary);
    const result = await this.llm.generateStructured(request, technologyPlanSchema);
    if (!result.ok) {
      this.logger.warn("planner.technology.failed", { provider: result.provider, errors: result.errors });
      return { technologies: [] };
    }
    this.logger.info("planner.technology.planned", {
      provider: result.provider,
      count: result.value.technologies.length,
      intent,
      targets,
    });
    return result.value;
  }
}
