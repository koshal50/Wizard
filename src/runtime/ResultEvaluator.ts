/**
 * ResultEvaluator — DETERMINISTIC hypothesis evaluation.
 *
 * This is the heart of "minimise LLM calls". Given a completed node and the
 * Observation it produced, it decides — with NO model call — whether the result
 * is:
 *   - SUCCESS    → the node's successClaim applies.
 *   - FAILURE    → the node's failureClaim applies.
 *   - UNEXPECTED → neither hypothesis cleanly holds; the Runtime may escalate.
 *
 * Only UNEXPECTED results ever reach the Planner. Every node type has a fixed,
 * inspectable rule here.
 */
import type { EvaluationResult, InvestigationNode, Observation } from "../core/types.ts";

export interface EvaluatedNode extends EvaluationResult {
  /** machine-readable reason code, for the runtime's escalation policy. */
  reasonCode:
    | "ok"
    | "nonzero_exit"
    | "execution_disabled"
    | "timed_out"
    | "file_missing"
    | "parse_failed"
    | "no_matches"
    | "unsupported"
    | "no_template"
    | "error";
}

export function evaluateNode(node: InvestigationNode, observation: Observation): EvaluatedNode {
  const d = observation.data as Record<string, unknown>;

  if (observation.type === "error") {
    return unexpected(node, "error", `node produced an error observation`);
  }

  switch (node.action.type) {
    case "execute":
      return evaluateExecute(node, d);
    case "read":
      return evaluateRead(node, d);
    case "parse":
      return evaluateParse(node, d);
    case "discovery":
      return evaluateDiscovery(node, d);
    case "verify":
      return evaluateVerify(node, d);
    case "synthesize":
      return success(node, "ok", "synthesis produced");
    case "planner":
    case "checkpoint":
      // These are orchestrated directly by the Runtime, not through the generic
      // evaluator; treat as neutral success so the loop can proceed.
      return success(node, "ok", `${node.action.type} node processed`);
    default:
      return unexpected(node, "no_template", "unknown action type");
  }
}

function evaluateExecute(node: InvestigationNode, d: Record<string, unknown>): EvaluatedNode {
  const exitCode = d.exitCode as number | null;
  const timedOut = d.timedOut === true;
  if (timedOut) return unexpected(node, "timed_out", "command timed out");
  if (exitCode === null) {
    // Either execution disabled or the process could not be spawned.
    const stderr = String(d.stderr ?? "");
    if (stderr.includes("[execution disabled]")) {
      return unexpected(node, "execution_disabled", "execution disabled for this investigation");
    }
    return unexpected(node, "execution_disabled", "command could not be executed");
  }
  if (exitCode === 0) return success(node, "ok", "command exited 0");
  return failure(node, "nonzero_exit", `command exited ${exitCode}`);
}

function evaluateRead(node: InvestigationNode, d: Record<string, unknown>): EvaluatedNode {
  if (d.exists === true) return success(node, "ok", "file present");
  return failure(node, "file_missing", "file not found");
}

function evaluateParse(node: InvestigationNode, d: Record<string, unknown>): EvaluatedNode {
  if (d.ok === true) return success(node, "ok", "parsed successfully");
  return failure(node, "parse_failed", `parse failed: ${String(d.error ?? "unknown")}`);
}

function evaluateDiscovery(node: InvestigationNode, d: Record<string, unknown>): EvaluatedNode {
  const matches = Array.isArray(d.matches) ? d.matches : [];
  if (matches.length > 0) return success(node, "ok", `${matches.length} match(es)`);
  return failure(node, "no_matches", "no matches found");
}

function evaluateVerify(node: InvestigationNode, d: Record<string, unknown>): EvaluatedNode {
  if (d.supported === true) return success(node, "ok", "evidence supports claim");
  return failure(node, "unsupported", "evidence does not support claim");
}

// ── builders ──────────────────────────────────────────────────────────────────

function success(node: InvestigationNode, reasonCode: EvaluatedNode["reasonCode"], reason: string): EvaluatedNode {
  return {
    outcome: "SUCCESS",
    reason,
    reasonCode,
    claimTemplate: node.successClaim,
  };
}

function failure(node: InvestigationNode, reasonCode: EvaluatedNode["reasonCode"], reason: string): EvaluatedNode {
  return {
    outcome: "FAILURE",
    reason,
    reasonCode,
    claimTemplate: node.failureClaim,
  };
}

function unexpected(node: InvestigationNode, reasonCode: EvaluatedNode["reasonCode"], reason: string): EvaluatedNode {
  return { outcome: "UNEXPECTED", reason, reasonCode };
}
