/**
 * Read Node — Tier 2 of progressive context. Reads the FULL contents of ONE
 * specific file, safely (path confined to the repo root). Produces a
 * file_content Observation.
 */
import fs from "node:fs/promises";
import type { InvestigationNode, ReadAction } from "../core/types.ts";
import type { NodeExecutionContext, NodeExecutionResult, NodeExecutor } from "./InvestigationNode.ts";
import { resolveInsideRepo } from "../util/safety.ts";

const MAX_READ_BYTES = 512 * 1024; // never load an enormous file into context

export const readExecutor: NodeExecutor = {
  actionType: "read",
  async execute(node: InvestigationNode, ctx: NodeExecutionContext): Promise<NodeExecutionResult> {
    const action = node.action as ReadAction;
    const safe = resolveInsideRepo(ctx.repoRoot, action.filePath);
    if (!safe.ok || !safe.resolved) {
      throw new Error(`Read rejected: ${safe.reason ?? "unsafe path"}`);
    }
    try {
      const stat = await fs.stat(safe.resolved);
      if (!stat.isFile()) {
        return {
          observationType: "file_content",
          data: { filePath: action.filePath, content: "", bytes: 0, exists: false },
        };
      }
      const buf = await fs.readFile(safe.resolved);
      const sliced = buf.subarray(0, MAX_READ_BYTES);
      ctx.logger.debug("read.executed", { file: action.filePath, bytes: sliced.length });
      return {
        observationType: "file_content",
        data: {
          filePath: action.filePath,
          content: sliced.toString("utf8"),
          bytes: stat.size,
          exists: true,
        },
      };
    } catch {
      return {
        observationType: "file_content",
        data: { filePath: action.filePath, content: "", bytes: 0, exists: false },
      };
    }
  },
};
