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

export function toManifestSummary(manifest: RepositoryManifest): ManifestSummary {
  return {
    languages: manifest.languages,
    frameworks: manifest.frameworks,
    packageManagers: manifest.packageManagers,
    dependencies: manifest.dependencies,
    databases: manifest.databases,
    keyFiles: manifest.keyFiles.map((k) => k.path),
    entryFiles: manifest.entryFiles,
    projectType: manifest.projectType,
  };
}

export class TechnologyPlanner {
  private readonly llm: LLMProvider;
  private readonly logger: Logger;

  constructor(llm: LLMProvider, logger: Logger) {
    this.llm = llm;
    this.logger = logger;
  }

  async plan(manifest: RepositoryManifest): Promise<TechnologyPlan> {
    const request = buildTechnologyPlanPrompt(renderManifestForPrompt(manifest), toManifestSummary(manifest));
    const result = await this.llm.generateStructured(request, technologyPlanSchema);
    if (!result.ok) {
      this.logger.warn("planner.technology.failed", { provider: result.provider, errors: result.errors });
      return { technologies: [] };
    }
    this.logger.info("planner.technology.planned", {
      provider: result.provider,
      count: result.value.technologies.length,
    });
    return result.value;
  }
}
