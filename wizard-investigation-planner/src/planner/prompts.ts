/**
 * Planner prompts.
 *
 * Three SEPARATE prompt builders — one per planner responsibility — each
 * producing a complete `LLMRequest`. Every request carries:
 *   - `prompt`/`system`: natural-language instructions for a hosted model, with
 *     a strict "return ONLY JSON matching this shape" contract.
 *   - `context`: the same information in structured form, consumed by the
 *     offline HeuristicLLMProvider.
 *
 * The prompts describe the OUTPUT CONTRACT but never include the whole repo —
 * only the compact, progressive context (Tier 1 manifest / Tier 2 excerpts /
 * Tier 3 recent results). This is the "Planner never receives the whole repo"
 * rule made concrete.
 */
import type { LLMRequest } from "../llm/LLMProvider.ts";
import type { ManifestSummary } from "./contextTypes.ts";
import type { EscalationContext, PlannerContext } from "../core/types.ts";

const JSON_ONLY = "Respond with ONLY a single JSON object. No prose, no markdown fences.";

const PLANNER_ROLE =
  "You are the Investigation Planner for a code-verification engine. You do NOT read files, run commands, or decide truth. You ONLY propose the next structured investigation nodes. The Runtime executes them and owns all results.";

// ── 1. Technology plan (initial) ──────────────────────────────────────────────

export function buildTechnologyPlanPrompt(
  manifestText: string,
  manifestSummary: ManifestSummary,
): LLMRequest {
  const question = questionBlock(manifestSummary);
  const localArchitecture = ['investigate', 'explain'].includes(manifestSummary.intent.trim())
    && manifestSummary.targets.includes('architecture');
  const prompt = [
    "Given this repository manifest (Tier-1 context only), identify the technologies",
    "present and, for each, the initial verification goals and the highest-priority",
    "files to inspect.",
    "Keep verification strictly within the requested intent, targets and question.",
    ...(localArchitecture ? [
      "This is a LOCAL SOURCE ARCHITECTURE investigation. Declare one goal: Inspect Architecture.",
      "Its evidence is repository reads, not application execution. Do not declare runtime/service readiness goals.",
      "Choose 3-6 existing implementation entry points showing component ownership and data flow, not only dependency manifests.",
      "Do not start services, perform network verification, or require UI execution for this source analysis.",
    ] : []),
    "Declare each requested goal once across the entire plan, not once per technology.",
    "Use concise goal names such as Verify Runtime, Verify Web Surface or Operate Web Surface when applicable.",
    "Incidental technologies may have empty initialGoals and priorityFiles. Do not add linting, deployment, database migrations or test suites unless requested or necessary prerequisites.",
    "Select only the minimum files needed to choose the first safe action; later planning receives real observations.",
    ...question,
    "",
    "MANIFEST:",
    manifestText,
    "",
    "Return JSON of the form:",
    `{"technologies":[{"name":"technology name","confidence":"medium","signals":["manifest signal"],"initialGoals":["initial verification goal"],"priorityFiles":["path/to/file"]}]}`,
    "",
    JSON_ONLY,
  ].join("\n");

  return {
    purpose: "technology_plan",
    system: PLANNER_ROLE,
    prompt,
    context: { manifest: manifestSummary },
    temperature: 0,
  };
}

/**
 * What the user asked for, rendered for the prompt.
 *
 * The manifest is identical for every investigation of a repository; this block
 * is the only part of the initial prompt that differs between them. Omitting it
 * is what let a plan ignore the question entirely.
 *
 * The command and the question are two lines because they are two facts. The
 * command says what kind of answer is wanted — an investigation may run things
 * to understand them, a report may not run anything at all — and the question
 * says what it is about. Rendering the command as "what the user wants to know"
 * is what this used to do, and "explain" is not something anyone wants to know.
 */
function questionBlock(summary: ManifestSummary): string[] {
  const lines: string[] = [];
  if (summary.intent.trim()) {
    lines.push("", `COMMAND: ${summary.intent.trim()}`);
  }
  if (summary.question.trim()) {
    lines.push(`THE USER'S QUESTION, VERBATIM: ${summary.question.trim()}`);
  }
  if (summary.targets.length > 0) {
    lines.push(
      `NAMED TARGETS: ${summary.targets.join(", ")}`,
      "Treat each named target as a subject to investigate, and resolve it to",
      "concrete files from the file list below (`priorityFiles`).",
    );
  }
  if (lines.length > 0) {
    lines.push(
      "Every goal you propose must be answerable by evidence this repository can",
      "actually yield: a file that exists, a command that runs, a page that loads.",
    );
  }
  return lines;
}

// ── 2. Ongoing plan (fill the current goal's gaps) ────────────────────────────

export function buildOngoingPlanPrompt(
  context: PlannerContext,
  heuristicContext: Record<string, unknown>,
): LLMRequest {
  const goal = context.currentGoal;
  const missing = context.openQuestions.map((q) => `- ${q.question} (need claim: ${q.missingClaimType})`).join("\n");
  const knownClaims = context.knowledgeGraph.claims
    .map((c) => `- ${c.type} = ${c.value} (trust ${c.trust.toFixed(2)})`)
    .join("\n");
  const recentNodes = context.recentInvestigationNodes
    .map((n) => `- ${n.nodeId} ${n.type} [${n.status}${n.outcome ? "/" + n.outcome : ""}] ${n.hypothesis}`)
    .join("\n");
  const readFiles = Object.entries(context.repositoryContext.readFiles)
    .map(([path, excerpt]) => `- ${path}: ${excerpt}`)
    .join("\n");

  const prompt = [
    `Current goal: ${goal.name} (technology: ${goal.technology}, status: ${goal.status}).`,
    `Requirements:\n${goal.requirements.map((r) => `- ${r}`).join("\n") || "- (none)"}`,
    "",
    `Open questions (what is still missing):\n${missing || "- (none)"}`,
    "",
    `Known claims:\n${knownClaims || "- (none yet)"}`,
    "",
    `Recent investigation nodes:\n${recentNodes || "- (none)"}`,
    "",
    `Files already read (excerpts):\n${readFiles || "- (none)"}`,
    "",
    `Budget: ${context.budget.nodeExecutionsRemaining} node executions remaining.`,
    "",
    "Propose the next investigation nodes to close the open questions. Prefer cheap",
    "deterministic steps (read → parse) before execution. Only propose execute nodes",
    "when a runtime fact genuinely requires running something.",
    "Use successful_results, actual failure reasons and process_sessions from the Runtime state.",
    "A foreground server timeout is not proof that startup failed; use an owned background process and its observed output.",
    "Do not repeat completed/rejected actions. If execution evidence is missing, propose a distinct executable recovery node, not more already-read files.",
    'Action types are read or execute, NEVER evidence categories such as command_execution or process_execution.',
    'An execution proposal uses {"type":"execute","action":{"type":"execute","command":"<observed package script or entry command>","workingDirectory":"<repository-relative directory>","timeoutMs":30000},"hypothesis":"<runtime fact to check>"}. Explorer selects the concrete execution tool.',
    "",
    "Return JSON of the form:",
    `{"nodes":[{"type":"read","action":{"type":"read","filePath":"package.json"},"hypothesis":"Inspect the project start configuration."}],"rationale":"Inspect startup configuration."}`,
    "",
    JSON_ONLY,
  ].join("\n");

  return {
    purpose: "ongoing_plan",
    system: PLANNER_ROLE,
    prompt,
    context: heuristicContext,
    temperature: 0,
  };
}

// ── 3. Escalation (recover from an UNEXPECTED result) ─────────────────────────

export function buildEscalationPrompt(
  escalation: EscalationContext,
  heuristicContext: Record<string, unknown>,
): LLMRequest {
  const prompt = [
    "An investigation node produced an UNEXPECTED result (it neither confirmed nor",
    "cleanly refuted its hypothesis). Decide the minimal recovery step(s).",
    "",
    `Node: ${escalation.node.nodeId} (${escalation.node.type})`,
    `Hypothesis: ${escalation.hypothesis}`,
    `Observation: ${escalation.observation.summary}`,
    `Current goal: ${escalation.currentGoal.name} (${escalation.currentGoal.technology})`,
    `Budget: ${escalation.budget.nodeExecutionsRemaining} node executions remaining.`,
    "",
    "Be conservative: at most one additional read if it would clarify things, else",
    "return an empty node list (record-only). Do NOT guess.",
    "",
    "Return JSON of the form:",
    `{"nodes":[...],"rationale":string}`,
    "",
    JSON_ONLY,
  ].join("\n");

  return {
    purpose: "escalation",
    system: PLANNER_ROLE,
    prompt,
    context: heuristicContext,
    temperature: 0,
  };
}
