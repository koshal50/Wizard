/**
 * Execute Node — Tier 3 of progressive context. Runs a command inside the
 * sandbox via the injected CommandRunner and produces a command_result
 * Observation (exit code / stdout / stderr / timing). The command has already
 * passed `checkCommandSafety` at scheduling time; the working directory is
 * confined to the repo root here as a defense in depth.
 */
import type { ExecuteAction, InvestigationNode } from "../core/types.ts";
import type { NodeExecutionContext, NodeExecutionResult, NodeExecutor } from "./InvestigationNode.ts";
import { checkCommandSafety, resolveInsideRepo } from "../util/safety.ts";

const DEFAULT_TIMEOUT_MS = 60_000;

export const executeExecutor: NodeExecutor = {
  actionType: "execute",
  async execute(node: InvestigationNode, ctx: NodeExecutionContext): Promise<NodeExecutionResult> {
    const action = node.action as ExecuteAction;

    const cmdSafety = checkCommandSafety(action.command);
    if (!cmdSafety.ok) {
      throw new Error(`Execute rejected: ${cmdSafety.reason}`);
    }

    const wd = action.workingDirectory ?? ".";
    const safeWd = resolveInsideRepo(ctx.repoRoot, wd);
    if (!safeWd.ok || !safeWd.resolved) {
      throw new Error(`Execute rejected: ${safeWd.reason ?? "unsafe working directory"}`);
    }

    if (!ctx.allowExecution) {
      // Execution disabled (e.g. --no-exec or Docker unavailable). Record a
      // command_result Observation marked as skipped so the hypothesis evaluator
      // classifies it as UNEXPECTED rather than fabricating success/failure.
      ctx.logger.warn("execute.skipped", { command: action.command, reason: "execution disabled" });
      return {
        observationType: "command_result",
        data: {
          command: action.command,
          workingDirectory: safeWd.resolved,
          exitCode: null,
          stdout: "",
          stderr: "[execution disabled] command not run",
          timedOut: false,
          durationMs: 0,
        },
      };
    }

    const timeoutMs = action.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    const result = await ctx.commandRunner.run(action.command, safeWd.resolved, timeoutMs);
    ctx.logger.debug("execute.executed", {
      command: action.command,
      exitCode: result.exitCode,
      timedOut: result.timedOut,
    });
    return { observationType: "command_result", data: result };
  },
};
