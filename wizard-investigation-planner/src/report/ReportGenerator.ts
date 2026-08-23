/**
 * ReportGenerator — turns a completed `InvestigationResult` into the Final
 * Investigation Report (Markdown) and, optionally, persists it to disk.
 *
 * The RuntimeEngine deliberately does NOT render or persist reports itself (see
 * its `reporting` state comment): it hands back a pure `InvestigationResult` and
 * the caller (the CLI) uses this generator. That keeps the engine free of I/O
 * beyond the investigation itself.
 *
 * Design notes:
 *   - The report shows BOTH graphs, kept visibly separate, matching the
 *     architecture: "Knowledge Graph = what we know", "Investigation Graph = how
 *     we found it".
 *   - Every claim is printed WITH its trust, status, and provenance (source node
 *     + observation) so the report is auditable end-to-end (§ claim provenance).
 *   - The investigation tree is rendered by REUSING `InvestigationGraph.render()`
 *     rather than re-implementing tree walking — the result snapshot is rehydrated
 *     into a throwaway graph purely for rendering.
 *   - `render()` is pure (no I/O, deterministic given inputs); `persist()` is the
 *     only method that touches the filesystem.
 */
import fs from "node:fs/promises";
import path from "node:path";
import type {
  Claim,
  ClaimRelationship,
  Goal,
  InvestigationNode,
  InvestigationResult,
  Observation,
  TechnologyPlan,
} from "../core/types.ts";
import { InvestigationGraph } from "../graphs/InvestigationGraph.ts";

export interface ReportOptions {
  /** Original repository path, for the header (not present on the result). */
  repositoryPath?: string;
  /** Which LLM provider drove the planner, for the header/audit trail. */
  provider?: string;
  /** Injectable timestamp so the report is deterministic in tests. */
  generatedAt?: string;
  /** Cap observations listed in the appendix. Default 40. */
  maxObservations?: number;
}

export interface PersistResult {
  reportPath: string;
  snapshotPath: string;
}

const DEFAULT_REPORT_NAME = "verification_report.md";
const DEFAULT_SNAPSHOT_NAME = "investigation.json";

export class ReportGenerator {
  /** Render the full Markdown report. Pure — no filesystem access. */
  render(result: InvestigationResult, opts: ReportOptions = {}): string {
    const sections: string[] = [];
    sections.push(this.header(result, opts));
    sections.push(this.summary(result));
    sections.push(this.goals(result.goals));
    sections.push(this.technologyPlan(result.technologyPlan));
    sections.push(this.knowledge(result.knowledgeGraph.claims, result.knowledgeGraph.relationships));
    sections.push(this.investigation(result.investigationGraph.nodes));
    sections.push(this.observations(result.observations, opts.maxObservations ?? 40));
    return sections.filter((s) => s.length > 0).join("\n\n") + "\n";
  }

  /**
   * Render + write the report and a JSON snapshot to `artifactDir`. Returns the
   * absolute paths written. Creates the directory if needed.
   */
  async persist(
    result: InvestigationResult,
    artifactDir: string,
    opts: ReportOptions = {},
  ): Promise<PersistResult> {
    const markdown = this.render(result, opts);
    await fs.mkdir(artifactDir, { recursive: true });

    const reportPath = path.join(artifactDir, DEFAULT_REPORT_NAME);
    const snapshotPath = path.join(artifactDir, DEFAULT_SNAPSHOT_NAME);

    await fs.writeFile(reportPath, markdown, "utf8");
    await fs.writeFile(snapshotPath, JSON.stringify(this.snapshot(result), null, 2), "utf8");

    return { reportPath, snapshotPath };
  }

  // ── sections ────────────────────────────────────────────────────────────────

  private header(result: InvestigationResult, opts: ReportOptions): string {
    const lines = [
      `# Investigation Report`,
      ``,
      `- **Investigation**: \`${result.investigationId}\``,
      `- **State**: ${stateBadge(result.state)} ${result.state}`,
      `- **Termination**: ${result.terminationReason}`,
    ];
    if (opts.repositoryPath) lines.push(`- **Repository**: \`${opts.repositoryPath}\``);
    if (opts.provider) lines.push(`- **Planner provider**: ${opts.provider}`);
    if (opts.generatedAt) lines.push(`- **Generated**: ${opts.generatedAt}`);
    return lines.join("\n");
  }

  private summary(result: InvestigationResult): string {
    const s = result.statistics;
    return [
      `## Summary`,
      ``,
      `| Metric | Value |`,
      `| --- | ---: |`,
      `| Goals satisfied | ${s.goalsSatisfied} / ${s.goalsTotal} |`,
      `| Nodes executed | ${s.nodesExecuted} |`,
      `| Planner calls | ${s.plannerCalls} |`,
      `| Claims created | ${s.claimsCreated} |`,
      `| Observations | ${s.observationsCreated} |`,
    ].join("\n");
  }

  private goals(goals: Goal[]): string {
    if (goals.length === 0) return `## Goals\n\n_No goals were established._`;
    const lines = [`## Goals`, ``];
    for (const g of goals) {
      lines.push(`### ${goalBadge(g.status)} ${g.name}  —  ${g.technology}`);
      lines.push(``);
      lines.push(`Status: **${g.status}**`);
      lines.push(``);
      for (const req of g.requirements) {
        lines.push(`- \`${req.claimType}\` — ${req.description}`);
      }
      lines.push(``);
    }
    return lines.join("\n").trimEnd();
  }

  private technologyPlan(plan: TechnologyPlan | null): string {
    if (!plan || plan.technologies.length === 0) {
      return `## Technology Plan\n\n_No technologies were planned._`;
    }
    const lines = [`## Technology Plan`, ``];
    for (const t of plan.technologies) {
      lines.push(`### ${t.name}  _(confidence: ${t.confidence})_`);
      lines.push(``);
      if (t.signals.length) lines.push(`- **Signals**: ${t.signals.join(", ")}`);
      if (t.initialGoals.length) lines.push(`- **Initial goals**: ${t.initialGoals.join(", ")}`);
      if (t.priorityFiles.length) lines.push(`- **Priority files**: ${t.priorityFiles.map(code).join(", ")}`);
      lines.push(``);
    }
    return lines.join("\n").trimEnd();
  }

  /** Knowledge Graph — WHAT WE KNOW. Claims with trust + provenance, then edges. */
  private knowledge(claims: Claim[], relationships: ClaimRelationship[]): string {
    const lines = [`## Knowledge Graph — What We Know`, ``];
    if (claims.length === 0) {
      lines.push(`_No claims were established._`);
      return lines.join("\n");
    }
    lines.push(`| Claim | Value | Trust | Status | Evidence | Provenance |`);
    lines.push(`| --- | --- | ---: | --- | ---: | --- |`);
    for (const c of sortClaims(claims)) {
      lines.push(
        `| \`${c.type}\` | ${escapeCell(c.value)} | ${c.trust.toFixed(2)} | ${claimStatusBadge(c.status)} ${c.status} | ${c.evidence.length} | ${provenanceCell(c)} |`,
      );
    }
    if (relationships.length) {
      lines.push(``);
      lines.push(`**Relationships**`);
      lines.push(``);
      for (const r of relationships) {
        lines.push(`- \`${r.from}\` **${r.type}** \`${r.to}\``);
      }
    }
    return lines.join("\n");
  }

  /** Investigation Graph — HOW WE FOUND IT. Reuses the graph's own renderer. */
  private investigation(nodes: InvestigationNode[]): string {
    const lines = [`## Investigation Graph — How We Found It`, ``];
    if (nodes.length === 0) {
      lines.push(`_No investigation nodes were created._`);
      return lines.join("\n");
    }
    // Rehydrate a throwaway graph so we reuse InvestigationGraph.render() rather
    // than duplicating the ASCII-tree logic.
    const graph = new InvestigationGraph();
    for (const n of nodes) {
      if (!graph.hasNode(n.nodeId)) graph.addNode(n);
    }
    lines.push("```text");
    lines.push(graph.render());
    lines.push("```");
    return lines.join("\n");
  }

  private observations(observations: Observation[], max: number): string {
    const lines = [`## Observations`, ``];
    if (observations.length === 0) {
      lines.push(`_No observations were recorded._`);
      return lines.join("\n");
    }
    const shown = observations.slice(0, max);
    lines.push(`| Observation | Node | Type | Summary |`);
    lines.push(`| --- | --- | --- | --- |`);
    for (const o of shown) {
      lines.push(
        `| \`${o.observationId}\` | \`${o.nodeId}\` | ${o.type} | ${escapeCell(summarizeObservation(o))} |`,
      );
    }
    if (observations.length > shown.length) {
      lines.push(``);
      lines.push(`_… and ${observations.length - shown.length} more observation(s)._`);
    }
    return lines.join("\n");
  }

  // ── JSON snapshot ─────────────────────────────────────────────────────────────

  private snapshot(result: InvestigationResult): unknown {
    return {
      investigationId: result.investigationId,
      state: result.state,
      terminationReason: result.terminationReason,
      statistics: result.statistics,
      technologyPlan: result.technologyPlan,
      goals: result.goals,
      knowledgeGraph: result.knowledgeGraph,
      investigationGraph: result.investigationGraph,
      claims: result.claims,
      observations: result.observations,
    };
  }
}

// ── formatting helpers ──────────────────────────────────────────────────────────

function code(s: string): string {
  return `\`${s}\``;
}

function escapeCell(s: string): string {
  return s.replace(/\|/g, "\\|").replace(/\r?\n/g, " ");
}

function provenanceCell(c: Claim): string {
  return `\`${c.provenance.sourceNodeId}\` / \`${c.provenance.observationId}\``;
}

function sortClaims(claims: Claim[]): Claim[] {
  return claims.slice().sort((a, b) => a.type.localeCompare(b.type));
}

function stateBadge(state: InvestigationResult["state"]): string {
  switch (state) {
    case "completed":
      return "✅";
    case "failed":
      return "❌";
    case "cancelled":
      return "⛔";
    default:
      return "ℹ️";
  }
}

function goalBadge(status: Goal["status"]): string {
  switch (status) {
    case "satisfied":
      return "✅";
    case "unsatisfiable":
      return "❌";
    case "in_progress":
      return "⏳";
    default:
      return "•";
  }
}

function claimStatusBadge(status: Claim["status"]): string {
  switch (status) {
    case "asserted":
      return "✅";
    case "contested":
      return "⚠️";
    case "refuted":
      return "❌";
    default:
      return "•";
  }
}

function summarizeObservation(o: Observation): string {
  const d = o.data as Record<string, unknown>;
  switch (o.type) {
    case "file_content":
      return `${String(d.filePath)} (${d.exists ? `${d.bytes}B` : "missing"})`;
    case "command_result":
      return `\`${String(d.command)}\` exit=${d.exitCode === null ? "n/a" : d.exitCode}${d.timedOut ? " (timed out)" : ""}`;
    case "parse_result":
      return `parse(${String(d.parser)}) ok=${d.ok}`;
    case "discovery_result":
      return `matched ${Array.isArray(d.matches) ? d.matches.length : 0} path(s)`;
    case "verify_result":
      return `supported=${d.supported}`;
    case "synthesis_result":
      return `synthesized ${String(d.inputCount ?? 0)} input(s)`;
    case "error":
      return `error: ${String(d.message)}`;
    default:
      return o.type;
  }
}
