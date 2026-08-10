# Wizard — Investigation Planner

LLM-powered **Investigation Planner** inside a deterministic **Runtime**, built on the
two-graph architecture (Knowledge Graph + Investigation Graph).

> The Runtime owns truth. The Planner informs the investigation.

Full documentation is generated at the end of the build (architecture, lifecycle, node
types, CLI usage, environment variables). See `docs/ARCHITECTURE.md`.

## Quick start

```bash
pnpm install --offline        # typescript + @types/node (devDeps only; zero runtime deps)
pnpm typecheck                # strict tsc, noEmit
pnpm test                     # node:test unit + integration suites
pnpm demo                     # end-to-end investigation on the bundled sample repo
```

## CLI

```bash
node src/cli/wizard.ts verify runtime ./sample-repos/sample-node-project
```

Runs fully offline by default via the deterministic `heuristic` LLM provider.
