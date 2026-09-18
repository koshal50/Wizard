/**
 * Wire contracts — the snake_case shapes the Python Wizard Runtime Kernel
 * deserializes. Authoritative source:
 *   wizard-runtime-engine/src/wizard_kernel/contracts/{plan,node,manifest}.py
 *   wizard-runtime-engine/src/wizard_kernel/ports/planner.py (HttpPlanner)
 *   wizard-runtime-engine/src/wizard_kernel/world/tools.py   (registered tools)
 *
 * This module is the ONE boundary that maps the Planner's internal (camelCase,
 * discriminated-action) proposals to the kernel's Pydantic contracts. The
 * Planner brain stays unchanged; only this edge translates.
 *
 * The Planner emits ONLY proposal fields. Runtime-owned fields (state,
 * observation_ids, claim_ids, ...) are left unset so Pydantic fills their
 * defaults — the Planner never asserts them (invariant: Planner plans, Runtime
 * owns truth). The internal PlannerValidator has already rejected any proposal
 * that tried to smuggle runtime-owned fields BEFORE it reaches here.
 */
import { randomUUID } from "node:crypto";
import type { ClaimTemplate, NodeAction, PlannerNodeProposal, TechnologyPlan } from "../core/types.ts";
import type { RepositoryManifest } from "../manifest/types.ts";
import { goalEvidenceFor } from "../planner/goalPolicy.ts";
import { newNodeId } from "../planner/interactionScript.ts";

// ── Wire shapes (snake_case; match the Pydantic models) ──────────────────────

export interface WireManifest {
  investigation_id: string;
  root_path: string;
  total_files: number;
  total_dirs: number;
  key_files: string[];
  extensions: Record<string, number>;
  directory_tree: string[];
  size_bytes_approx: number;
}

export interface WireHypothesis {
  kind: string;
  success_values?: unknown[];
  failure_values?: unknown[];
}

export interface WireClaimTemplate {
  claim_type: string;
  key: string;
  value: unknown;
}

export interface WireNode {
  id: string;
  type: string;
  action: { tool: string; params: Record<string, unknown> };
  hypothesis: WireHypothesis;
  on_success: WireClaimTemplate | null;
  on_failure: WireClaimTemplate | null;
  depends_on: string[];
  parent_id: string | null;
  goal_id: string | null;
}

export interface WireGoalDefinition {
  name: string;
  required_claim_types: string[];
  belief_threshold: number;
  requires_execution_evidence: boolean;
}

export interface WireTechnologyEntry {
  name: string;
  confidence: string;
  signals: string[];
  initial_goals: WireGoalDefinition[];
  priority_files: string[];
}

export interface WireTechnologyPlan {
  technologies: WireTechnologyEntry[];
  seed_nodes: WireNode[];
}

// __APPEND_MARKER__

// ── Manifest: Python (wire) → internal TS RepositoryManifest ─────────────────
// The kernel scanner emits only structural metadata (key_files, extensions,
// directory_tree). The heuristic technology planner keys off key file names, so
// we map those through faithfully and derive coarse languages from extensions.

const EXT_LANG: Record<string, string> = {
  ".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript", ".jsx": "JavaScript",
  ".py": "Python", ".go": "Go", ".rs": "Rust", ".java": "Java", ".rb": "Ruby", ".php": "PHP",
};

function extOf(path: string): string {
  const i = path.lastIndexOf(".");
  return i >= 0 ? path.slice(i) : "";
}

function basename(p: string): string {
  const parts = p.replace(/\\/g, "/").split("/").filter(Boolean);
  return parts.length ? parts[parts.length - 1]! : p;
}

function languagesFromExtensions(exts: Record<string, number>): string[] {
  const langs = new Set<string>();
  for (const ext of Object.keys(exts)) {
    const key = ext.startsWith(".") ? ext : "." + ext;
    const lang = EXT_LANG[key.toLowerCase()];
    if (lang) langs.add(lang);
  }
  return [...langs];
}

export function manifestFromWire(m: WireManifest): RepositoryManifest {
  const keyFiles = (m.key_files ?? []).map((p) => ({ path: p, sizeBytes: 0, extension: extOf(p) }));
  return {
    repositoryName: basename(m.root_path ?? ""),
    rootPath: m.root_path ?? "",
    fileCount: m.total_files ?? 0,
    directoryCount: m.total_dirs ?? 0,
    languages: languagesFromExtensions(m.extensions ?? {}),
    frameworks: [],
    packageManagers: [],
    dependencies: [],
    databases: [],
    keyFiles,
    entryFiles: [],
    extensions: m.extensions ?? {},
    projectType: "unknown",
    // The kernel's `directory_tree` is a list of *files* — world/scanner.py
    // appends `rel_file` for every file it walks past. It used to be mapped
    // into `structure.directories`, which meant the one field that claims to
    // list directories held file paths, and there was no field at all holding
    // the file list. Reading a named target is the thing that needed the
    // latter, so it is named for what it is here; the kernel sends no
    // directory list to put in the former.
    treeFiles: m.directory_tree ?? [],
    structure: { directories: [], importantPaths: [], folders: [], applications: [] },
  };
}

// ── Node id + action/hypothesis/claim mapping ────────────────────────────────

export function nodeId(): string {
  return newNodeId();
}

/**
 * Map an internal discriminated action to a kernel {tool, params} pair using the
 * tool names registered in world/tools.py. Returns null for action types that
 * have no registered agent tool (parse/verify/synthesize/planner/checkpoint) —
 * those are handled Runtime-side, not dispatched as tools, so proposing them as
 * executable nodes would be rejected. Such proposals are dropped, not smuggled.
 */
function actionToWire(a: NodeAction): { tool: string; params: Record<string, unknown> } | null {
  switch (a.type) {
    case "read":
      return { tool: "read_file", params: { path: a.filePath, max_bytes: 65536 } };
    case "execute": {
      const params: Record<string, unknown> = { command: a.command };
      if (a.workingDirectory) params.cwd = a.workingDirectory;
      if (typeof a.timeoutMs === "number") params.timeout_sec = Math.max(1, Math.ceil(a.timeoutMs / 1000));
      return { tool: "execute_command", params };
    }
    case "discovery":
      return { tool: "search_files", params: { pattern: a.pattern, glob: a.directory ? `${a.directory}/**/*` : "**/*" } };
    case "browser":
      // The kernel's browser tools take no arguments beyond the ones named here
      // (world/tools.py): snapshot/extract/back are nullary. Sending only the
      // parameters the tool actually reads keeps the validator's structural check
      // meaningful instead of passing extra keys through it.
      switch (a.tool) {
        case "navigate": return { tool: "browser_navigate", params: { url: a.url } };
        case "click":    return { tool: "browser_click", params: { selector: a.selector } };
        case "type":     return { tool: "browser_type", params: { selector: a.selector, text: a.text ?? "" } };
        case "snapshot": return { tool: "browser_snapshot", params: {} };
        case "extract":  return { tool: "browser_extract", params: {} };
        case "back":     return { tool: "browser_back", params: {} };
        default:         return null;
      }
    default:
      return null;
  }
}

function hypothesisFor(a: NodeAction): WireHypothesis {
  // execute → deterministic exit-code check (exit 0 = success); read/discovery
  // always produce an observation, so success is structural.
  // browser → always_success for the same reason: a browser action always yields an
  // observation, and the WEB claims come from the kernel's extractors reading it,
  // not from this node's own success template. `http_status` would look stricter
  // but never fires — it reads payload.status_code, while a navigation result
  // carries its status at payload.data.status.
  return a.type === "execute"
    ? { kind: "exit_code_in", success_values: [0] }
    : { kind: "always_success" };
}

function actionKey(a: NodeAction): string {
  switch (a.type) {
    case "read": return a.filePath;
    case "execute": return a.command;
    case "discovery": return a.pattern;
    case "browser": return a.tool === "navigate" ? (a.url ?? "browser") : `browser:${a.tool}`;
    default: return a.type;
  }
}

function claimToWire(t: ClaimTemplate | undefined, key: string): WireClaimTemplate | null {
  if (!t) return null;
  // trustWeight/relationships are intentionally dropped — trust is Runtime-owned.
  return { claim_type: t.type, key, value: t.value };
}

/** Map a validated proposal to a kernel InvestigationNode, or null if not tool-executable. */
export function proposalToWire(p: PlannerNodeProposal): WireNode | null {
  const action = actionToWire(p.action);
  if (!action) return null;
  const key = actionKey(p.action);
  return {
    id: p.nodeId ?? nodeId(),
    type: p.type,
    action,
    hypothesis: hypothesisFor(p.action),
    on_success: claimToWire(p.successClaim, key),
    on_failure: claimToWire(p.failureClaim, key),
    depends_on: p.dependencies ?? [],
    parent_id: p.parentNodeId ?? null,
    goal_id: p.goalId ?? null,
  };
}

export function proposalsToWire(proposals: PlannerNodeProposal[]): WireNode[] {
  return proposals.map(proposalToWire).filter((n): n is WireNode => n !== null);
}

// ── Technology plan: internal → wire ─────────────────────────────────────────
// GoalDefinition.required_claim_types is derived from the goal name using the
// same claim-type vocabulary as the kernel's MockPlanner (RUNTIME / PACKAGE /
// DEPLOYMENT / FILESYSTEM). This mapping is the one contract detail to confirm
// with the Runtime team; the SHAPE matches contracts/plan.py exactly.
//
// Every claim type named here must be one the kernel's extractors can actually
// produce (belief/extractors.py), from an action the plan can actually propose.
// A goal whose evidence cannot exist is unsatisfiable by construction, and it
// reads identically to a goal the run failed to prove — see the container note
// below. `FILE_READ` is in that vocabulary too: it is what a read node asserts
// through its own on_success template, and the loop admits it through the
// EvidenceEngine like any other claim (loop.py, the expected_success case).

export function goalDefFor(name: string): WireGoalDefinition {
  const evidence = goalEvidenceFor(name);
  return {
    name,
    required_claim_types: evidence.required_claim_types,
    belief_threshold: 0.6,
    requires_execution_evidence: evidence.requires_execution_evidence,
  };
}

function seedReadNode(path: string): WireNode {
  return {
    id: nodeId(),
    type: "read",
    action: { tool: "read_file", params: { path, max_bytes: 65536 } },
    hypothesis: { kind: "always_success" },
    on_success: { claim_type: "FILE_READ", key: path, value: true },
    on_failure: null,
    depends_on: [],
    parent_id: null,
    goal_id: null,
  };
}

/**
 * The initial browser frontier: navigate → snapshot → extract, chained.
 *
 * Three nodes rather than one because each yields different WEB claims from the
 * kernel's extractors: navigate gives current_url / http_status:<url> / page_title,
 * snapshot gives a11y_node_count, extract gives has_text_content. A single navigate
 * would leave the "Verify Web Surface" goal permanently open — the kernel's goal
 * engine counts claim types, and one navigation produces only some of them.
 */
export function browserSeedNodes(url: string): WireNode[] {
  const nav = nodeId();
  const snap = nodeId();
  return [
    {
      id: nav, type: "browser",
      action: { tool: "browser_navigate", params: { url } },
      hypothesis: { kind: "always_success" },
      on_success: null, on_failure: null, depends_on: [], parent_id: null, goal_id: "goal_web",
    },
    {
      id: snap, type: "browser",
      action: { tool: "browser_snapshot", params: {} },
      hypothesis: { kind: "always_success" },
      on_success: null, on_failure: null, depends_on: [nav], parent_id: null, goal_id: "goal_web",
    },
    {
      id: nodeId(), type: "browser",
      action: { tool: "browser_extract", params: {} },
      hypothesis: { kind: "always_success" },
      on_success: null, on_failure: null, depends_on: [snap], parent_id: null, goal_id: "goal_web",
    },
  ];
}

export function technologyPlanToWire(
  plan: TechnologyPlan,
  browserTargets: string[] = [],
  operatesSurface = false,
): WireTechnologyPlan {
  const technologies: WireTechnologyEntry[] = plan.technologies.map((t) => ({
    name: t.name,
    confidence: t.confidence,
    signals: t.signals,
    initial_goals: t.initialGoals.map(goalDefFor),
    priority_files: t.priorityFiles,
  }));

  // Seed one read node per distinct priority file so the Runtime has an initial
  // frontier (mirrors MockPlanner.initial's seed_nodes).
  const seen = new Set<string>();
  const seed_nodes: WireNode[] = [];
  for (const t of plan.technologies) {
    for (const f of t.priorityFiles) {
      if (seen.has(f)) continue;
      seen.add(f);
      seed_nodes.push(seedReadNode(f));
    }
  }

  // A named URL is a target with no files behind it, so it contributes no priority
  // file and would otherwise seed nothing at all. The browser target is a Runtime
  // capability, so this only happens when a plane actually exists — the caller
  // passes browserTargets only when browser_enabled is true.
  if (browserTargets.length > 0) {
    // Seeded browser nodes are only meaningful if a goal requires WEB claims;
    // otherwise they run, admit evidence, and close nothing. The heuristic provider
    // declares this technology itself, but a real-LLM provider may not, so the edge
    // guarantees the two halves agree rather than trusting the provider to.
    const hasWebGoal = technologies.some((t) =>
      t.initial_goals.some((g) => g.required_claim_types.includes("WEB")));
    if (!hasWebGoal) {
      // "Verify Web Surface" is closed by reaching a page; "Operate Web Surface"
      // only by acting on one, because the kernel types an interaction's claims
      // INTERACTION and a navigate produces none. Both are declared when the
      // request asks for the app to be operated, and the second is what stops the
      // run finishing the moment the page loads — which is exactly what it did
      // while reaching a page was the only thing a browser goal could ask for.
      //
      // Filtered against what the plan already carries: the provider attaches a
      // requested goal to the plan's primary technology before this edge runs, so
      // pushing both unconditionally would declare "Operate Web Surface" twice —
      // two goals one piece of evidence closes, and a report that says a thing
      // was proved twice.
      const carried = new Set<string>();
      for (const t of technologies) for (const g of t.initial_goals) carried.add(g.name);
      const wanted = operatesSurface
        ? ["Verify Web Surface", "Operate Web Surface"]
        : ["Verify Web Surface"];
      technologies.push({
        name: "Web",
        confidence: "high",
        signals: browserTargets.map((u) => `target: ${u}`),
        initial_goals: wanted.filter((n) => !carried.has(n)).map(goalDefFor),
        priority_files: [],
      });
    }
    seed_nodes.push(...browserSeedNodes(browserTargets[0]!));
  }

  return { technologies, seed_nodes };
}
