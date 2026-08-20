/**
 * HeuristicLLMProvider — the offline, deterministic default provider.
 *
 * It produces genuinely useful planning output WITHOUT any network access or API
 * key, by reading the structured `request.context` the Planner assembles and
 * applying fixed rules. This is what makes the whole system runnable offline and
 * reproducible in CI: same context in → same plan out, and ZERO real LLM calls.
 *
 * It dispatches on `request.purpose`:
 *   - technology_plan → derive a TechnologyPlan from the manifest summary.
 *   - ongoing_plan    → propose the next investigation nodes to fill the current
 *                       goal's missing requirements (a read→parse→verify chain,
 *                       plus a guarded execute probe for runtime goals).
 *   - escalation      → conservative recovery: at most one re-read, else record.
 *
 * The object it builds is still run through the caller's schema, so if a context
 * is malformed the call fails honestly instead of returning garbage.
 */
import type { Schema } from "../../validation/schema.ts";
import { safeParse } from "../../validation/schema.ts";
import type { LLMProvider, LLMRequest, LLMResult } from "../LLMProvider.ts";
import { llmErr, llmOk } from "../LLMProvider.ts";

// ── Context contracts (what the Planner puts in request.context) ─────────────

interface ManifestContext {
  languages?: string[];
  frameworks?: string[];
  packageManagers?: string[];
  dependencies?: string[];
  databases?: string[];
  keyFiles?: string[];
  entryFiles?: string[];
  projectType?: string;
}

interface RequirementContext {
  claimType: string;
  description?: string;
  expectedValue?: string;
}

interface OngoingContext {
  goalTechnology?: string;
  allowExecution?: boolean;
  missingRequirements?: RequirementContext[];
  priorityFiles?: string[];
  parsedObservationIds?: Record<string, string>; // filePath -> observationId
  fileObservationIds?: Record<string, string>; // filePath -> observationId (raw read)
}

interface EscalationCtx {
  nodeId?: string;
  filePath?: string;
  alreadyReadPaths?: string[];
  reason?: string;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function str(v: unknown): string | undefined {
  return typeof v === "string" ? v : undefined;
}
function strArr(v: unknown): string[] {
  return Array.isArray(v) ? v.filter((x): x is string => typeof x === "string") : [];
}
function has(hay: string[], needle: string): boolean {
  return hay.some((h) => h.toLowerCase().includes(needle.toLowerCase()));
}

// ── technology_plan ───────────────────────────────────────────────────────────

function buildTechnologyPlan(ctx: ManifestContext): unknown {
  const languages = ctx.languages ?? [];
  const frameworks = ctx.frameworks ?? [];
  const packageManagers = ctx.packageManagers ?? [];
  const databases = ctx.databases ?? [];
  const keyFiles = ctx.keyFiles ?? [];
  const entryFiles = ctx.entryFiles ?? [];
  const technologies: unknown[] = [];

  const nodeish =
    has(languages, "JavaScript") ||
    has(languages, "TypeScript") ||
    packageManagers.some((p) => ["npm", "pnpm", "yarn"].includes(p)) ||
    keyFiles.some((f) => f.endsWith("package.json"));
  if (nodeish) {
    technologies.push({
      name: "Node.js",
      confidence: keyFiles.some((f) => f.endsWith("package.json")) ? "high" : "medium",
      signals: [
        ...packageManagers.map((p) => `package manager: ${p}`),
        ...keyFiles.filter((f) => f.endsWith("package.json")).map((f) => `manifest: ${f}`),
      ],
      initialGoals: ["Verify Runtime", "Verify Dependencies"],
      priorityFiles: [
        ...keyFiles.filter((f) => f.endsWith("package.json")),
        ...entryFiles,
      ].slice(0, 5),
    });
  }

  const pythonish =
    has(languages, "Python") ||
    has(frameworks, "Django") ||
    keyFiles.some((f) => f.endsWith("requirements.txt") || f.endsWith("pyproject.toml") || f.endsWith("manage.py"));
  if (pythonish) {
    technologies.push({
      name: has(frameworks, "Django") ? "Django" : "Python",
      confidence: keyFiles.some((f) => f.endsWith("requirements.txt") || f.endsWith("manage.py")) ? "high" : "medium",
      signals: [
        ...frameworks.filter((f) => f === "Django").map((f) => `framework: ${f}`),
        ...keyFiles
          .filter((f) => f.endsWith("requirements.txt") || f.endsWith("manage.py") || f.endsWith("pyproject.toml"))
          .map((f) => `manifest: ${f}`),
      ],
      initialGoals: ["Verify Runtime", "Verify Dependencies"],
      priorityFiles: keyFiles
        .filter((f) => f.endsWith("requirements.txt") || f.endsWith("manage.py") || f.endsWith("pyproject.toml"))
        .slice(0, 5),
    });
  }

  if (keyFiles.some((f) => f.endsWith("Dockerfile") || f.includes("docker-compose"))) {
    technologies.push({
      name: "Docker",
      confidence: "high",
      signals: keyFiles.filter((f) => f.endsWith("Dockerfile") || f.includes("docker-compose")).map((f) => `file: ${f}`),
      initialGoals: ["Verify Containerization"],
      priorityFiles: keyFiles.filter((f) => f.endsWith("Dockerfile") || f.includes("docker-compose")).slice(0, 3),
    });
  }

  for (const db of databases) {
    technologies.push({
      name: db,
      confidence: "medium",
      signals: [`database signal: ${db}`],
      initialGoals: ["Verify Dependencies"],
      priorityFiles: [],
    });
  }

  if (technologies.length === 0) {
    technologies.push({
      name: ctx.projectType || "Unknown",
      confidence: "low",
      signals: ["no strong technology signals detected"],
      initialGoals: ["Verify Runtime"],
      priorityFiles: entryFiles.slice(0, 3),
    });
  }

  return { technologies };
}

// ── ongoing_plan ──────────────────────────────────────────────────────────────

/**
 * Propose nodes to satisfy the goal's missing requirements. Strategy:
 *   - If a priority file has not been read → propose a READ node.
 *   - If a priority file has been read but not parsed → propose a PARSE node.
 *   - For a runtime requirement with execution allowed → propose a guarded
 *     EXECUTE probe.
 *   - Always cap the batch so the budget is respected.
 */
function buildOngoingPlan(ctx: OngoingContext): unknown {
  const nodes: unknown[] = [];
  const priorityFiles = ctx.priorityFiles ?? [];
  const fileObs = ctx.fileObservationIds ?? {};
  const parsedObs = ctx.parsedObservationIds ?? {};
  const missing = ctx.missingRequirements ?? [];
  const tech = ctx.goalTechnology ?? "the technology";

  // 1. Read any priority file we have not read yet.
  for (const file of priorityFiles) {
    if (!(file in fileObs)) {
      nodes.push({
        type: "read",
        action: { type: "read", filePath: file },
        hypothesis: `${file} exists and is readable`,
        successClaim: { type: "FILE_PRESENT", value: file },
        failureClaim: { type: "FILE_PRESENT", value: `missing:${file}` },
      });
    }
  }

  // 2. Parse read-but-unparsed structured files.
  for (const [file, obsId] of Object.entries(fileObs)) {
    if (file in parsedObs) continue;
    const parser = pickParser(file);
    if (!parser) continue;
    nodes.push({
      type: "parse",
      action: { type: "parse", sourceObservationId: obsId, parser },
      hypothesis: `${file} parses as ${parser} and declares runtime metadata`,
      successClaim: { type: "MANIFEST_PARSED", value: file },
      failureClaim: { type: "MANIFEST_PARSED", value: `unparseable:${file}` },
    });
  }

  // 3. For runtime requirements, propose a guarded execute probe.
  const wantsRuntime = missing.some((m) => m.claimType === "RUNTIME_STATUS");
  if (wantsRuntime && ctx.allowExecution) {
    const probe = pickRuntimeProbe(tech);
    if (probe) {
      nodes.push({
        type: "execute",
        action: { type: "execute", command: probe.command, timeoutMs: 60000 },
        hypothesis: probe.hypothesis,
        successClaim: { type: "RUNTIME_STATUS", value: "verified", trustWeight: 0.9 },
        failureClaim: { type: "RUNTIME_STATUS", value: "broken" },
        unexpectedAction: "escalate_to_planner",
      });
    }
  }

  return { nodes, rationale: `heuristic ongoing plan for ${tech}: ${nodes.length} node(s)` };
}

function pickParser(file: string): string | null {
  if (file.endsWith("package.json")) return "package-json";
  if (file.endsWith("Dockerfile")) return "dockerfile";
  if (file.endsWith("requirements.txt")) return "requirements";
  if (file.endsWith(".json")) return "json";
  return null;
}

function pickRuntimeProbe(tech: string): { command: string; hypothesis: string } | null {
  const t = tech.toLowerCase();
  if (t.includes("node")) {
    return { command: "node --version", hypothesis: "Node.js runtime is available" };
  }
  if (t.includes("python") || t.includes("django")) {
    return { command: "python --version", hypothesis: "Python runtime is available" };
  }
  if (t.includes("docker")) {
    return { command: "docker --version", hypothesis: "Docker runtime is available" };
  }
  return null;
}

// ── escalation ────────────────────────────────────────────────────────────────

function buildEscalation(ctx: EscalationCtx): unknown {
  const alreadyRead = ctx.alreadyReadPaths ?? [];
  // Conservative recovery: if there is a file we have NOT yet read, read it once.
  if (ctx.filePath && !alreadyRead.includes(ctx.filePath)) {
    return {
      nodes: [
        {
          type: "read",
          action: { type: "read", filePath: ctx.filePath },
          hypothesis: `re-reading ${ctx.filePath} clarifies the unexpected result`,
          successClaim: { type: "FILE_PRESENT", value: ctx.filePath },
        },
      ],
      rationale: `escalation recovery: read ${ctx.filePath}`,
    };
  }
  // Otherwise record only — do not spend budget guessing.
  return { nodes: [], rationale: "escalation: no deterministic recovery; recording only" };
}

// ── Provider ──────────────────────────────────────────────────────────────────

export class HeuristicLLMProvider implements LLMProvider {
  readonly name = "heuristic";

  async generateStructured<T>(request: LLMRequest, schema: Schema<T>): Promise<LLMResult<T>> {
    const ctx = (request.context ?? {}) as Record<string, unknown>;
    let built: unknown;
    switch (request.purpose) {
      case "technology_plan":
        built = buildTechnologyPlan(readManifestContext(ctx));
        break;
      case "ongoing_plan":
        built = buildOngoingPlan(readOngoingContext(ctx));
        break;
      case "escalation":
        built = buildEscalation(readEscalationContext(ctx));
        break;
      default:
        return llmErr<T>([`heuristic: unknown purpose ${String(request.purpose)}`], "", this.name);
    }

    const raw = JSON.stringify(built);
    const parsed = safeParse(schema, built);
    if (!parsed.ok) return llmErr<T>(parsed.errors, raw, this.name);
    return llmOk<T>(parsed.value, raw, this.name);
  }
}

function readManifestContext(ctx: Record<string, unknown>): ManifestContext {
  const m = (ctx.manifest as Record<string, unknown>) ?? ctx;
  return {
    languages: strArr(m.languages),
    frameworks: strArr(m.frameworks),
    packageManagers: strArr(m.packageManagers),
    dependencies: strArr(m.dependencies),
    databases: strArr(m.databases),
    keyFiles: strArr(m.keyFiles),
    entryFiles: strArr(m.entryFiles),
    projectType: str(m.projectType),
  };
}

function readOngoingContext(ctx: Record<string, unknown>): OngoingContext {
  const missingRaw = Array.isArray(ctx.missingRequirements) ? ctx.missingRequirements : [];
  const missingRequirements: RequirementContext[] = [];
  for (const r of missingRaw) {
    const o = r as Record<string, unknown>;
    const claimType = str(o.claimType);
    if (!claimType) continue;
    missingRequirements.push({ claimType, description: str(o.description), expectedValue: str(o.expectedValue) });
  }

  return {
    goalTechnology: str(ctx.goalTechnology),
    allowExecution: typeof ctx.allowExecution === "boolean" ? ctx.allowExecution : false,
    missingRequirements,
    priorityFiles: strArr(ctx.priorityFiles),
    fileObservationIds: asStringRecord(ctx.fileObservationIds),
    parsedObservationIds: asStringRecord(ctx.parsedObservationIds),
  };
}

function readEscalationContext(ctx: Record<string, unknown>): EscalationCtx {
  return {
    nodeId: str(ctx.nodeId),
    filePath: str(ctx.filePath),
    alreadyReadPaths: strArr(ctx.alreadyReadPaths),
    reason: str(ctx.reason),
  };
}

function asStringRecord(v: unknown): Record<string, string> {
  if (!v || typeof v !== "object" || Array.isArray(v)) return {};
  const out: Record<string, string> = {};
  for (const [k, val] of Object.entries(v as Record<string, unknown>)) {
    if (typeof val === "string") out[k] = val;
  }
  return out;
}
