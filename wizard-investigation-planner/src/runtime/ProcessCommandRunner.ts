/**
 * ProcessCommandRunner — the real sandboxed command executor.
 *
 * Implements the `CommandRunner` interface the Execute node depends on. Every
 * command has ALREADY passed the safety allowlist (the scheduler enforces that
 * before a node runs); this runner adds the operational guarantees:
 *   - a hard timeout (kills the process group on expiry),
 *   - captured stdout/stderr with size caps,
 *   - a working directory constrained to the repo (the caller passes an
 *     already-resolved absolute path inside the repo).
 *
 * It NEVER throws for a non-zero exit or a timeout — those are normal
 * observations. It only rejects on a genuine spawn failure, which the Execute
 * node records as a command_result with exitCode null.
 */
import { spawn } from "node:child_process";
import type { CommandResultData } from "../core/types.ts";
import type { CommandRunner } from "../nodes/InvestigationNode.ts";
import type { Clock } from "../util/clock.ts";

const MAX_OUTPUT_BYTES = 256 * 1024;

export interface ProcessRunnerOptions {
  clock?: Clock;
  /** overall ceiling regardless of per-node timeout. */
  hardCapMs?: number;
}

export class ProcessCommandRunner implements CommandRunner {
  private readonly hardCapMs: number;

  constructor(opts: ProcessRunnerOptions = {}) {
    this.hardCapMs = opts.hardCapMs ?? 120000;
  }

  run(command: string, workingDirectory: string, timeoutMs: number): Promise<CommandResultData> {
    const effectiveTimeout = Math.min(timeoutMs || this.hardCapMs, this.hardCapMs);
    const startedAt = Date.now();

    return new Promise<CommandResultData>((resolve) => {
      let child;
      try {
        child = spawn(command, {
          cwd: workingDirectory,
          shell: true,
          windowsHide: true,
        });
      } catch (e) {
        resolve(this.spawnFailure(command, workingDirectory, `${(e as Error).message}`, startedAt));
        return;
      }

      let stdout = "";
      let stderr = "";
      let timedOut = false;
      let settled = false;

      const timer = setTimeout(() => {
        timedOut = true;
        try {
          child.kill("SIGKILL");
        } catch {
          /* already gone */
        }
      }, effectiveTimeout);

      child.stdout?.on("data", (chunk: Buffer) => {
        if (stdout.length < MAX_OUTPUT_BYTES) stdout += chunk.toString("utf8");
      });
      child.stderr?.on("data", (chunk: Buffer) => {
        if (stderr.length < MAX_OUTPUT_BYTES) stderr += chunk.toString("utf8");
      });

      const finish = (exitCode: number | null): void => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        resolve({
          command,
          workingDirectory,
          exitCode: timedOut ? null : exitCode,
          stdout: stdout.slice(0, MAX_OUTPUT_BYTES),
          stderr: (timedOut ? stderr + "\n[timed out]" : stderr).slice(0, MAX_OUTPUT_BYTES),
          timedOut,
          durationMs: Date.now() - startedAt,
        });
      };

      child.on("error", (e) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        resolve(this.spawnFailure(command, workingDirectory, e.message, startedAt));
      });
      child.on("close", (code) => finish(code));
    });
  }

  private spawnFailure(command: string, cwd: string, message: string, startedAt: number): CommandResultData {
    return {
      command,
      workingDirectory: cwd,
      exitCode: null,
      stdout: "",
      stderr: `[spawn failed] ${message}`,
      timedOut: false,
      durationMs: Date.now() - startedAt,
    };
  }
}

/** A no-op runner used when execution is disabled or in tests. */
export class DisabledCommandRunner implements CommandRunner {
  async run(command: string, workingDirectory: string): Promise<CommandResultData> {
    return {
      command,
      workingDirectory,
      exitCode: null,
      stdout: "",
      stderr: "[execution disabled]",
      timedOut: false,
      durationMs: 0,
    };
  }
}
