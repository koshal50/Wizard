/**
 * Parse Node — deterministic structured extraction from a PRIOR observation
 * (usually a Read node's file_content). No LLM. Produces a parse_result
 * Observation whose `parsed` field holds the structured data.
 */
import type { InvestigationNode, ParseAction } from "../core/types.ts";
import type { NodeExecutionContext, NodeExecutionResult, NodeExecutor } from "./InvestigationNode.ts";

type ParserFn = (content: string) => Record<string, unknown>;

/** Parse a package.json into the fields the planner/evaluators care about. */
const parsePackageJson: ParserFn = (content) => {
  const pkg = JSON.parse(content) as Record<string, unknown>;
  const scripts = (pkg.scripts as Record<string, string>) ?? {};
  const deps = Object.keys((pkg.dependencies as object) ?? {});
  const devDeps = Object.keys((pkg.devDependencies as object) ?? {});
  return {
    name: pkg.name ?? null,
    version: pkg.version ?? null,
    main: pkg.main ?? null,
    type: pkg.type ?? "commonjs",
    startScript: scripts.start ?? null,
    buildScript: scripts.build ?? null,
    testScript: scripts.test ?? null,
    scripts,
    dependencies: deps,
    devDependencies: devDeps,
    engines: pkg.engines ?? null,
  };
};

const parseDockerfile: ParserFn = (content) => {
  const lines = content.split(/\r?\n/).map((l) => l.trim()).filter((l) => l && !l.startsWith("#"));
  const from = lines.find((l) => /^FROM /i.test(l))?.replace(/^FROM /i, "").trim() ?? null;
  const exposes = lines
    .filter((l) => /^EXPOSE /i.test(l))
    .flatMap((l) => l.replace(/^EXPOSE /i, "").trim().split(/\s+/));
  const cmd = lines.find((l) => /^CMD /i.test(l))?.replace(/^CMD /i, "").trim() ?? null;
  const entrypoint = lines.find((l) => /^ENTRYPOINT /i.test(l))?.replace(/^ENTRYPOINT /i, "").trim() ?? null;
  return { baseImage: from, exposedPorts: exposes, cmd, entrypoint };
};

const parseRequirementsTxt: ParserFn = (content) => {
  const packages = content
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l && !l.startsWith("#"))
    .map((l) => l.split(/[=<>!~ ]/)[0]);
  return { packages };
};

const parseJson: ParserFn = (content) => {
  const value = JSON.parse(content) as unknown;
  return { value };
};

const parsers: Record<string, ParserFn> = {
  "package-json": parsePackageJson,
  dockerfile: parseDockerfile,
  requirements: parseRequirementsTxt,
  json: parseJson,
};

export const parseExecutor: NodeExecutor = {
  actionType: "parse",
  async execute(node: InvestigationNode, ctx: NodeExecutionContext): Promise<NodeExecutionResult> {
    const action = node.action as ParseAction;
    const source = ctx.observations.get(action.sourceObservationId);
    if (!source) {
      throw new Error(`Parse rejected: source observation ${action.sourceObservationId} not found`);
    }
    const data = source.data as { content?: string };
    const content = typeof data.content === "string" ? data.content : "";
    const parser = parsers[action.parser];
    if (!parser) {
      throw new Error(`Parse rejected: unknown parser "${action.parser}"`);
    }
    try {
      const parsed = parser(content);
      ctx.logger.debug("parse.executed", { parser: action.parser, keys: Object.keys(parsed) });
      return {
        observationType: "parse_result",
        data: { parser: action.parser, sourceObservationId: action.sourceObservationId, parsed, ok: true },
      };
    } catch (err) {
      return {
        observationType: "parse_result",
        data: {
          parser: action.parser,
          sourceObservationId: action.sourceObservationId,
          parsed: {},
          ok: false,
          error: (err as Error).message,
        },
      };
    }
  },
};
