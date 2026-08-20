/**
 * Path & command safety. LLM output is UNTRUSTED — every file path and command
 * proposed by the Planner passes through here before the Runtime acts on it.
 */
import path from "node:path";

export interface SafetyResult {
  ok: boolean;
  reason?: string;
  /** absolute, normalized path (for file ops) when ok. */
  resolved?: string;
}

/**
 * Resolve a repo-relative path and guarantee it stays inside the repo root.
 * Rejects absolute paths and `..` escapes.
 */
export function resolveInsideRepo(repoRoot: string, relative: string): SafetyResult {
  if (typeof relative !== "string" || relative.length === 0) {
    return { ok: false, reason: "empty path" };
  }
  if (relative.includes("\0")) return { ok: false, reason: "null byte in path" };
  // Normalize both to absolute and compare prefixes.
  const root = path.resolve(repoRoot);
  const candidate = path.resolve(root, relative);
  const rel = path.relative(root, candidate);
  if (rel === "" ) {
    // points at the repo root itself — allow (used for cwd of exec)
    return { ok: true, resolved: candidate };
  }
  if (rel.startsWith("..") || path.isAbsolute(rel)) {
    return { ok: false, reason: `path escapes repository root: ${relative}` };
  }
  return { ok: true, resolved: candidate };
}

/** Commands we refuse to run regardless of context (destructive / exfiltration). */
const DANGEROUS_PATTERNS: RegExp[] = [
  /\brm\s+-rf?\b/i,
  /\bmkfs\b/i,
  /\bdd\s+if=/i,
  /:\(\)\s*\{\s*:\|:&\s*\}/, // fork bomb
  /\bshutdown\b/i,
  /\breboot\b/i,
  /\bchmod\s+-R\s+777\b/i,
  /\bcurl\b[^\n]*\|\s*(sh|bash)\b/i,
  /\bwget\b[^\n]*\|\s*(sh|bash)\b/i,
  />\s*\/dev\/sd[a-z]/i,
  /\bgit\s+push\b/i,
];

/** Allowlist of command leaders we consider legitimate investigation actions. */
const ALLOWED_LEADERS = new Set([
  "npm",
  "pnpm",
  "yarn",
  "node",
  "npx",
  "python",
  "python3",
  "pip",
  "pip3",
  "pytest",
  "go",
  "cargo",
  "docker",
  "java",
  "mvn",
  "gradle",
  "ls",
  "cat",
  "echo",
  "true",
  "test",
]);

export function checkCommandSafety(command: string): SafetyResult {
  if (typeof command !== "string" || command.trim().length === 0) {
    return { ok: false, reason: "empty command" };
  }
  for (const pat of DANGEROUS_PATTERNS) {
    if (pat.test(command)) return { ok: false, reason: `command matched dangerous pattern: ${pat}` };
  }
  const leader = command.trim().split(/\s+/)[0] ?? "";
  // strip env-assignment prefixes like FOO=bar node ...
  const realLeader = /=/.test(leader) ? (command.trim().split(/\s+/).find((t) => !t.includes("=")) ?? "") : leader;
  const base = realLeader.split("/").pop() ?? realLeader;
  if (!ALLOWED_LEADERS.has(base)) {
    return { ok: false, reason: `command leader "${base}" is not in the allowlist` };
  }
  return { ok: true };
}
