/**
 * Verify Node — tests a specific existing claim against named evidence
 * (observations). Produces a verification_result Observation stating whether the
 * evidence supports the claim. It does NOT set trust — the Trust Engine does.
 */
import type { InvestigationNode, VerifyAction } from "../core/types.ts";
import type { NodeExecutionContext, NodeExecutionResult, NodeExecutor } from "./InvestigationNode.ts";

export const verifyExecutor: NodeExecutor = {
  actionType: "verify",
  async execute(node: InvestigationNode, ctx: NodeExecutionContext): Promise<NodeExecutionResult> {
    const action = node.action as VerifyAction;
    const evidence = action.evidenceIds
      .map((id) => ctx.observations.get(id))
      .filter((o): o is NonNullable<typeof o> => Boolean(o));

    const claim = action.claimId ? ctx.claims.get(action.claimId) : undefined;

    // Support = at least one execution observation succeeded, or any evidence present.
    const supporting = evidence.filter((o) => {
      if (o.type === "command_result") {
        const d = o.data as { exitCode: number | null };
        return d.exitCode === 0;
      }
      return true;
    });

    const supported = supporting.length > 0;
    ctx.logger.debug("verify.executed", {
      claimId: action.claimId,
      evidenceCount: evidence.length,
      supported,
    });
    return {
      observationType: "verify_result",
      data: {
        claimId: action.claimId ?? null,
        claimType: claim?.type ?? null,
        evidenceIds: action.evidenceIds,
        supportingCount: supporting.length,
        totalEvidence: evidence.length,
        supported,
      },
    };
  },
};
