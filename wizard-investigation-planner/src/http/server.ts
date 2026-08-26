/**
 * Planner HTTP service — the seam the Python kernel's HttpPlanner calls.
 *
 * Exposes exactly the three endpoints ports/planner.py::HttpPlanner POSTs to:
 *   POST /plan/initial   {manifest, intent, targets}  → TechnologyPlan
 *   POST /plan/next      <context packet>             → { new_nodes: [...] }
 *   POST /plan/interpret {node, observation}          → { new_nodes: [...] }
 *
 * It is a thin adapter: parse JSON → call the InvestigationPlanner brain →
 * translate the internal proposals to the kernel's snake_case Pydantic contracts
 * via ./contracts.ts. It owns no state, executes nothing, and never mutates
 * Runtime truth.
 *
 * Provider defaults to the offline `heuristic` (zero key, zero network). Set
 * LLM_PROVIDER=openai + LLM_BASE_URL=<vLLM url> for a real open-source model.
 * SECURITY: this service binds to 127.0.0.1 by default and has no auth — it is a
 * private sidecar for the kernel, not a public endpoint. Front it accordingly.
 */
import http from "node:http";
import { InvestigationPlanner } from "../planner/InvestigationPlanner.ts";
import { createProviderFromEnv } from "../llm/providerFactory.ts";
import { createLogger } from "../util/logger.ts";
import type { ValidationOptions } from "../planner/PlannerValidator.ts";
import type { PlannerContext, UserIntent, EscalationContext, InvestigationNodeType } from "../core/types.ts";
import {
  manifestFromWire,
  proposalsToWire,
  technologyPlanToWire,
  type WireManifest,
} from "./contracts.ts";

const logger = createLogger({ echo: true });
const planner = new InvestigationPlanner(createProviderFromEnv({ logger }), logger);

// ── Small JSON helpers (defensive: the /plan/next packet shape is a Runtime
// seam still under construction, so we read both snake_case and camelCase). ──
type Json = Record<string, unknown>;

function readBody(req: http.IncomingMessage): Promise<Json> {
  return new Promise((resolve, reject) => {
    let data = "";
    req.on("data", (c) => {
      data += c;
      if (data.length > 5_000_000) req.destroy(new Error("request body too large"));
    });
    req.on("end", () => {
      if (!data) return resolve({});
      try { resolve(JSON.parse(data) as Json); } catch (e) { reject(e as Error); }
    });
    req.on("error", reject);
  });
}

function pick(o: Json, ...keys: string[]): unknown {
  for (const k of keys) if (o[k] !== undefined) return o[k];
  return undefined;
}
function pickStr(o: Json, ...keys: string[]): string | undefined {
  const v = pick(o, ...keys);
  return typeof v === "string" ? v : undefined;
}
function pickNum(o: Json, ...keys: string[]): number | undefined {
  const v = pick(o, ...keys);
  return typeof v === "number" ? v : undefined;
}
function pickArr(o: Json, ...keys: string[]): unknown[] {
  const v = pick(o, ...keys);
  return Array.isArray(v) ? v : [];
}

/** ValidationOptions from the packet. allowExecution defaults to false (safe): the
 * validator will drop execute proposals until the Runtime packet opts in. */
function optsFrom(o: Json): ValidationOptions {
  return {
    repoRoot: pickStr(o, "repo_root", "root_path", "repositoryPath") ?? ".",
    budgetRemaining: pickNum(o, "budget_remaining", "remaining_budget", "budgetRemaining") ?? 25,
    allowExecution: pick(o, "allow_execution", "allowExecution") === true,
  };
}

/** The heuristic provider reads these keys; map the packet onto them. */
function heuristicFrom(o: Json): Record<string, unknown> {
  const missingRequirements = pickArr(o, "missing_requirements", "missingRequirements")
    .map((r) => {
      const m = r as Json;
      return {
        claimType: pickStr(m, "claim_type", "claimType"),
        description: pickStr(m, "description"),
        expectedValue: pick(m, "expected_value", "expectedValue"),
      };
    })
    .filter((m) => typeof m.claimType === "string");
  return {
    goalTechnology: pickStr(o, "goal_technology", "goalTechnology") ?? "unknown",
    allowExecution: pick(o, "allow_execution", "allowExecution") === true,
    missingRequirements,
    priorityFiles: pickArr(o, "priority_files", "priorityFiles").filter((x) => typeof x === "string"),
    fileObservationIds: (pick(o, "file_observation_ids", "fileObservationIds") as Json) ?? {},
    parsedObservationIds: (pick(o, "parsed_observation_ids", "parsedObservationIds") as Json) ?? {},
  };
}

/** A minimal, well-formed PlannerContext for prompt rendering (real-LLM path).
 * The heuristic provider ignores it and reads heuristicContext instead. */
function plannerContextFrom(o: Json, heuristic: Record<string, unknown>): PlannerContext {
  const budget = pickNum(o, "budget_remaining", "remaining_budget", "budgetRemaining") ?? 25;
  return {
    investigationId: pickStr(o, "investigation_id", "investigationId") ?? "inv_unknown",
    userIntent: (pickStr(o, "intent", "user_intent") ?? "investigate") as UserIntent,
    currentGoal: {
      goalId: pickStr(o, "goal_id", "goalId") ?? "goal",
      name: pickStr(o, "goal_name", "goalName") ?? "Investigate",
      technology: String(heuristic.goalTechnology ?? "unknown"),
      status: "in_progress",
      requirements: [],
    },
    knowledgeGraph: { claims: [] },
    recentInvestigationNodes: [],
    openQuestions: [],
    repositoryContext: { repositoryName: pickStr(o, "repository_name", "repositoryName") ?? "", keyFiles: [], readFiles: {} },
    recentObservations: [],
    budget: { nodeExecutionsRemaining: budget, plannerCallsRemaining: null },
  };
}

// ── Endpoint handlers ────────────────────────────────────────────────────────

async function handleInitial(body: Json): Promise<unknown> {
  const manifest = manifestFromWire((body.manifest ?? {}) as WireManifest);
  const plan = await planner.planTechnologies(manifest);
  return technologyPlanToWire(plan);
}

async function handleNext(body: Json): Promise<unknown> {
  const heuristicContext = heuristicFrom(body);
  const plannerContext = plannerContextFrom(body, heuristicContext);
  const batch = await planner.planNext({ plannerContext, heuristicContext }, optsFrom(body));
  return { new_nodes: proposalsToWire(batch.accepted) };
}

async function handleInterpret(body: Json): Promise<unknown> {
  const node = (body.node ?? {}) as Json;
  const obs = (body.observation ?? {}) as Json;
  const action = (node.action ?? {}) as Json;
  const params = (action.params ?? {}) as Json;
  const nodeIdV = pickStr(node, "id", "nodeId") ?? "node";
  const filePath = pickStr(params, "path");
  const reason = pickStr(obs, "error", "summary") ?? "unexpected result";

  const heuristicContext: Record<string, unknown> = {
    nodeId: nodeIdV,
    filePath,
    alreadyReadPaths: pickArr(body, "already_read_paths", "alreadyReadPaths").filter((x) => typeof x === "string"),
    reason,
  };
  const escalation: EscalationContext = {
    investigationId: pickStr(body, "investigation_id", "investigationId") ?? "inv_unknown",
    node: {
      nodeId: nodeIdV,
      type: (pickStr(node, "type") ?? "read") as InvestigationNodeType,
      action: pickStr(action, "tool") ?? "",
      hypothesis: "",
      status: "failed",
    },
    hypothesis: "",
    observation: {
      observationId: pickStr(obs, "id", "observation_id") ?? "obs",
      type: "error",
      summary: pickStr(obs, "summary", "error") ?? reason,
    },
    currentGoal: { goalId: "goal", name: "Investigate", technology: "unknown", status: "in_progress", requirements: [] },
    budget: { nodeExecutionsRemaining: pickNum(body, "budget_remaining", "remaining_budget") ?? 25, plannerCallsRemaining: null },
  };
  const batch = await planner.planEscalation(escalation, heuristicContext, optsFrom(body));
  return { new_nodes: proposalsToWire(batch.accepted) };
}

// ── Server ───────────────────────────────────────────────────────────────────

const routes: Record<string, (b: Json) => Promise<unknown>> = {
  "/plan/initial": handleInitial,
  "/plan/next": handleNext,
  "/plan/interpret": handleInterpret,
};

const server = http.createServer(async (req, res) => {
  const send = (code: number, obj: unknown) => {
    res.writeHead(code, { "content-type": "application/json" });
    res.end(JSON.stringify(obj));
  };
  const url = (req.url ?? "").split("?")[0]!;
  if (req.method === "GET" && url === "/health") return send(200, { ok: true });
  const handler = req.method === "POST" ? routes[url] : undefined;
  if (!handler) return send(404, { error: "not found" });
  try {
    const body = await readBody(req);
    send(200, await handler(body));
  } catch (e) {
    logger.warn("plan.request.failed", { url, error: (e as Error).message });
    send(400, { error: (e as Error).message });
  }
});

const PORT = Number(process.env.PLANNER_PORT ?? process.env.PORT ?? 8787);
const HOST = process.env.PLANNER_HOST ?? "127.0.0.1";
server.listen(PORT, HOST, () => logger.info("planner.listening", { host: HOST, port: PORT }));
