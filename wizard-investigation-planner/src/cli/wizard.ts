/**
 * wizard — the CLI composition root.
 *
 * This is the ONLY place that wires the concrete subsystems together:
 *
 *   provider (from env)  →  InvestigationPlanner  →  RuntimeEngine  →  result
 *                                                          │
 *                                                          ▼
 *                                                   ReportGenerator
 *
 * Everything below the CLI is pure/injectable (clock, ids, logger, provider), so
 * the engine itself never reads argv, env, or a wall clock directly. That keeps
 * the core deterministic and testable; the messy edges (arg parsing, .env, exit
 * codes, stdout) live here.
 *
 * Usage:
 *   node src/cli/wizard.ts <intent> [targets...] <repositoryPath> [flags]
 *
 *   intent   : investigate | verify | explain | report   (default: investigate)
 *   targets  : e.g. runtime dependencies containerization (optional)
 *   repoPath : path to the repository to investigate (required, last positional)
 *
 * Examples:
 *   node src/cli/wizard.ts verify runtime ./sample-repos/sample-node-project
 *   node src/cli/wizard.ts investigate ./some/repo --no-exec --json
 */
import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";

import type {
  InvestigationBudget,
  InvestigationConfiguration,
  InvestigationRequest,
  InvestigationResult,
  UserIntent,
} from "../core/types.ts";
import { RuntimeEngine } from "../runtime/RuntimeEngine.ts";
import { InvestigationPlanner } from "../planner/InvestigationPlanner.ts";
import { createProviderFromEnv, type ProviderEnv } from "../llm/providerFactory.ts";
import { ReportGenerator } from "../report/ReportGenerator.ts";
import { createIdFactory } from "../util/ids.ts";
import { systemClock } from "../util/clock.ts";
import { createLogger, type LogLevel } from "../util/logger.ts";

// ── argument parsing ─────────────────────────────────────────────────────────

const INTENTS: readonly UserIntent[] = ["investigate", "verify", "explain", "report"];

export interface CliFlags {
  help: boolean;
  json: boolean;
  noExec: boolean;
  noPersist: boolean;
  quiet: boolean;
  verbose: boolean;
  provider?: string;
  out?: string;
  budget?: number;
  plannerBudget?: number;
  timeout?: number;
}

export interface ParsedArgs {
  flags: CliFlags;
  positionals: string[];
}

function isIntent(s: string): s is UserIntent {
  return (INTENTS as readonly string[]).includes(s);
}

function toInt(v: string | undefined): number | undefined {
  if (v === undefined) return undefined;
  const n = Number.parseInt(v, 10);
  return Number.isFinite(n) ? n : undefined;
}

export function parseArgs(argv: string[]): ParsedArgs {
  const flags: CliFlags = {
    help: false,
    json: false,
    noExec: false,
    noPersist: false,
    quiet: false,
    verbose: false,
  };
  const positionals: string[] = [];

  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === undefined) continue;
    if (!arg.startsWith("-")) {
      positionals.push(arg);
      continue;
    }

    let key = arg.replace(/^--?/, "");
    let value: string | undefined;
    const eq = key.indexOf("=");
    if (eq >= 0) {
      value = key.slice(eq + 1);
      key = key.slice(0, eq);
    }
    const takeValue = (): string | undefined => value ?? argv[++i];

    switch (key) {
      case "h":
      case "help":
        flags.help = true;
        break;
      case "json":
        flags.json = true;
        break;
      case "no-exec":
        flags.noExec = true;
        break;
      case "no-persist":
        flags.noPersist = true;
        break;
      case "quiet":
        flags.quiet = true;
        break;
      case "verbose":
        flags.verbose = true;
        break;
      case "provider":
        flags.provider = takeValue();
        break;
      case "out":
        flags.out = takeValue();
        break;
      case "budget":
        flags.budget = toInt(takeValue());
        break;
      case "planner-budget":
        flags.plannerBudget = toInt(takeValue());
        break;
      case "timeout":
        flags.timeout = toInt(takeValue());
        break;
      default:
        // Unknown flag — ignore rather than crash; the usage text documents the set.
        break;
    }
  }

  return { flags, positionals };
}

// ── .env (best-effort, dependency-free) ──────────────────────────────────────

/**
 * Minimal `.env` loader: sets KEY=VALUE pairs into process.env if not already
 * present. No third-party dependency. Values are never logged (the logger also
 * redacts secrets defensively).
 */
async function loadDotEnv(dir: string): Promise<void> {
  let raw: string;
  try {
    raw = await fs.readFile(path.join(dir, ".env"), "utf8");
  } catch {
    return; // no .env — perfectly fine, heuristic provider needs no config
  }
  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eq = trimmed.indexOf("=");
    if (eq < 0) continue;
    const key = trimmed.slice(0, eq).trim();
    let val = trimmed.slice(eq + 1).trim();
    if (
      (val.startsWith('"') && val.endsWith('"')) ||
      (val.startsWith("'") && val.endsWith("'"))
    ) {
      val = val.slice(1, -1);
    }
    if (key && !(key in process.env)) process.env[key] = val;
  }
}

// ── usage ────────────────────────────────────────────────────────────────────

function printUsage(): void {
  const lines = [
    "wizard — repository investigation planner",
    "",
    "Usage:",
    "  wizard <intent> [targets...] <repositoryPath> [flags]",
    "",
    "Intent (default: investigate):",
    "  investigate | verify | explain | report",
    "",
    "Flags:",
    "  --provider <name>     Override LLM provider (heuristic|mock|anthropic|openai)",
    "  --budget <n>          Max node executions (default 60)",
    "  --planner-budget <n>  Max planner calls (default 25)",
    "  --timeout <ms>        Max execution time in ms (default 120000)",
    "  --out <dir>           Artifact directory (default <repo>/.wizard)",
    "  --no-exec             Disable command execution (no shell probes)",
    "  --no-persist          Do not write the report/snapshot to disk",
    "  --json                Print a JSON summary instead of the Markdown report",
    "  --verbose             Echo debug/info logs to stderr",
    "  --quiet               Suppress log echo",
    "  -h, --help            Show this help",
    "",
    "Examples:",
    "  wizard verify runtime ./sample-repos/sample-node-project",
    "  wizard investigate ./some/repo --no-exec --json",
  ];
  process.stdout.write(lines.join("\n") + "\n");
}

// ── main ───────────────────────────────────────────────────────────────────

function stderr(line: string): void {
  process.stderr.write(line + "\n");
}

function stateBadge(state: InvestigationResult["state"]): string {
  if (state === "completed") return "✔";
  if (state === "failed") return "✖";
  return "•";
}

/**
 * Exit-code policy:
 *   2 — the engine failed (crash / could not start).
 *   1 — a `verify` run finished but not all goals were satisfied (useful as a
 *       CI/healthcheck signal).
 *   0 — otherwise.
 */
export function exitCodeFor(result: InvestigationResult, intent: UserIntent): number {
  if (result.state === "failed") return 2;
  if (intent === "verify") {
    const { goalsSatisfied, goalsTotal } = result.statistics;
    if (goalsTotal > 0 && goalsSatisfied < goalsTotal) return 1;
  }
  return 0;
}

export async function main(argv: string[]): Promise<number> {
  const { flags, positionals } = parseArgs(argv);
  if (flags.help) {
    printUsage();
    return 0;
  }
  if (positionals.length === 0) {
    printUsage();
    return 1;
  }

  // First positional MAY be the intent; the LAST positional is always the path.
  let intent: UserIntent = "investigate";
  if (positionals.length > 1 && isIntent(positionals[0]!)) {
    intent = positionals.shift() as UserIntent;
  } else if (positionals.length === 1 && isIntent(positionals[0]!)) {
    // Only an intent given, no path.
    stderr("error: missing repository path");
    printUsage();
    return 1;
  }

  const rawPath = positionals.pop();
  if (rawPath === undefined) {
    stderr("error: missing repository path");
    printUsage();
    return 1;
  }
  const targets = positionals.slice();
  const repoPath = path.resolve(rawPath);

  // Validate the repository path up front for a clean error.
  try {
    const st = await fs.stat(repoPath);
    if (!st.isDirectory()) {
      stderr(`error: not a directory: ${repoPath}`);
      return 1;
    }
  } catch {
    stderr(`error: repository path does not exist: ${repoPath}`);
    return 1;
  }

  await loadDotEnv(process.cwd());

  const level: LogLevel = flags.verbose ? "debug" : "warn";
  const logger = createLogger({ level, echo: !flags.quiet });

  const env: ProviderEnv = { ...(process.env as ProviderEnv) };
  if (flags.provider) env.LLM_PROVIDER = flags.provider;
  const provider = createProviderFromEnv({ env, logger });

  const ids = createIdFactory();
  const planner = new InvestigationPlanner(provider, logger);
  const engine = new RuntimeEngine({ planner, logger, clock: systemClock(), ids });

  const budget: InvestigationBudget = {
    maxNodeExecutions: flags.budget ?? 60,
    executionsUsed: 0,
    maxPlannerCalls: flags.plannerBudget ?? 25,
    plannerCallsUsed: 0,
    maxExecutionTimeMs: flags.timeout ?? 120000,
  };

  const configuration: InvestigationConfiguration = {
    allowExecution: !flags.noExec,
    persist: !flags.noPersist,
    goalTrustThreshold: 0.6,
  };
  if (flags.out) configuration.artifactDir = flags.out;

  const request: InvestigationRequest = {
    investigationId: ids.next("inv"),
    userIntent: intent,
    repositoryPath: repoPath,
    investigationTargets: targets,
    budget,
    configuration,
  };

  stderr(`wizard: ${intent} ${targets.length ? targets.join(", ") + " " : ""}→ ${repoPath}`);
  stderr(`wizard: provider=${provider.name} exec=${configuration.allowExecution ? "on" : "off"}`);

  const result = await engine.run(request);

  const reportOpts = {
    repositoryPath: repoPath,
    provider: provider.name,
    generatedAt: new Date().toISOString(),
  };
  const report = new ReportGenerator();

  if (flags.json) {
    process.stdout.write(JSON.stringify(summarizeForJson(result), null, 2) + "\n");
  } else {
    process.stdout.write(report.render(result, reportOpts));
  }

  if (configuration.persist) {
    const artifactDir = configuration.artifactDir ?? path.join(repoPath, ".wizard");
    try {
      const { reportPath, snapshotPath } = await report.persist(result, artifactDir, reportOpts);
      stderr(`wizard: report  → ${reportPath}`);
      stderr(`wizard: snapshot → ${snapshotPath}`);
    } catch (e) {
      stderr(`wizard: could not persist report: ${(e as Error).message}`);
    }
  }

  const { goalsSatisfied, goalsTotal } = result.statistics;
  stderr(
    `\n${stateBadge(result.state)} ${result.state} — ${goalsSatisfied}/${goalsTotal} goals satisfied — ${result.terminationReason}`,
  );

  return exitCodeFor(result, intent);
}

function summarizeForJson(result: InvestigationResult): unknown {
  return {
    investigationId: result.investigationId,
    state: result.state,
    terminationReason: result.terminationReason,
    statistics: result.statistics,
    goals: result.goals.map((g) => ({
      name: g.name,
      technology: g.technology,
      status: g.status,
    })),
    claims: result.claims.map((c) => ({
      type: c.type,
      value: c.value,
      trust: c.trust,
      status: c.status,
    })),
  };
}

// ── entrypoint guard ─────────────────────────────────────────────────────────

const invokedDirectly =
  process.argv[1] !== undefined && import.meta.url === pathToFileURL(process.argv[1]).href;

if (invokedDirectly) {
  main(process.argv.slice(2))
    .then((code) => {
      process.exitCode = code;
    })
    .catch((e) => {
      process.stderr.write(`wizard: fatal: ${(e as Error).message}\n`);
      process.exitCode = 2;
    });
}
