# Architecture explorer refinement

The backend/runtime changes are in `fix/runtime-verification-integration`. Website changes are only in the sibling Wizard-web checkout on `wizar-web`. These refinements are not committed yet. The existing unrelated modification to `Wizard.code-workspace` is preserved.

## Diagnosis

The old coverage adapter promoted inspected source files into prominent module nodes and assigned folder boundaries. The viewer then drew all saved edges and fitted the complete graph into the viewport. This produced both noisy file maps and tiny labels. PostgreSQL/API retrieval preserved the graph; they were not dropping architectural metadata.

Initial repository selection also let nested documentation and example directories consume the small discovery/read budget. Startup behavior could be omitted from excerpts that favored imports. A separate finalization bug could report a completed architecture investigation after preparation checks passed even when final synthesis failed on the provider context limit.

## Generation and storage

The existing architecture synthesis now identifies evidence-backed subsystems and assigns important modules to them. Its adapter retains the inspected file graph beneath those modules and subsystems. It validates actual discovered/read paths and evidence references. Unique observed imports can extend file membership; shared or conflicting ownership remains unassigned and is disclosed. No relationship is added just because files share a folder.

Discovery prioritizes shallow project manifests and balances source inspection across top-level packages and their directories. Excerpts prioritize startup, route registration, database and API behavior alongside imports. Python imports resolve against discovered source/project roots only when unambiguous. An architecture-specific context packer shortens excerpts on complete lines to fit the existing provider budget, preserving observation IDs and reporting omitted context. Reader observations now record whether their content was truncated. Architecture finalization requires a successful architecture synthesis before reporting completion.

The additive schema extension keeps version 1 and accepts older investigations:

- Nodes: optional `parent_id`, and `level` (`subsystem`, `module`, or `file`).
- Relationships: concise, supported verb-led action labels, retaining classification and evidence.
- Coverage: discovered source candidates, examined source/context files, unread areas/counts, partial/older unmeasured reads, and unassigned source evidence.

Parent references, cycles, depth, paths, coverage consistency and existing graph/evidence constraints are validated. The existing `architecture_investigations.graph` PostgreSQL JSONB document stores all hierarchy, evidence and coverage. **No database migration, table, API, authentication mechanism, dependency, or CLI command was added.**

Existing backend routes remain:

- `POST /api/investigations`: authenticate, validate, persist and return the UUID.
- `GET /api/investigations`: list the authenticated owner's investigations.
- `GET /api/investigations/{investigation_id}`: return the authorized saved graph and evidence.

The CLI still uses `investigate architecture`, summarizes the data, obtains upload consent, uses existing authentication and prints the website URL only after successful persistence. Local retention remains unchanged. The website route is `/investigations/{id}`.

## Viewer

The overview shows saved subsystem boundaries instead of every inspected file. Expansion reveals modules and then file/evidence detail. Legacy saved groups remain expandable without modifying their stored graph.

Canonical relationships project to the visible boundary and aggregate into one directed arrow per boundary pair. No relationship is fabricated. Arrow labels expose supported actions such as `requests auth API` or `queries tasks DB`; additional labels and original supporting relationships remain selectable in the explorer. Node boxes contain concise names/types, not descriptive paragraphs. Selection emphasizes immediate connections and shows actual relative paths, classifications and evidence.

The deterministic layout collapses dependency cycles for ranking and places components in vertical bands with at most two columns. The canvas scrolls independently, preserves normal-size nodes, and supports drag pan, zoom, fit and reset. Orthogonal paths have at most three right-angle bends. Opposing same-level arrows use separate lanes so their labels do not overlap. Database nodes use the existing renderer's custom SVG cylinder with a light-orange fill. The evidence panel is collapsible and adapts to mobile screens.

Each detail level has explicit 24-component pagination, and ReactFlow renders visible elements. Canonical data remains available in the saved graph; the viewer states how many components/arrows are displayed and how many relationships are internal, outside the view, or filtered. This is client-side progressive presentation, not server-side lazy graph loading.

## Real repository verification

| Repository | Actual result | Coverage and visible overview |
| --- | --- | --- |
| Local `sample-project` | Completed, 42 saved nodes, 65 saved relationships | 3 subsystem overview: Client Package, Server Package, Database Layer. 33 of 37 source candidates read; 4 unread. |
| Local Wizard repository | Incomplete, 47 saved nodes, 20 saved relationships | 6 subsystem overview: Backend API, Frontend, Runtime, CLI, Planner Service and Database. 34 of 256 source candidates read; 222 unread. |

The sample overview has three bundled arrows rather than 65 simultaneous connections. Expansion exposes its API client and application modules and underlying source evidence. The larger repository is both a multi-package and larger-source validation case; it is not represented as a fully investigated repository.

Both actual exports were uploaded to an isolated PostgreSQL test schema and retrieved through the authenticated backend/website. Browser checks compare the retrieved graph with the export, exercise expansion/evidence/coverage, and verify anonymous and cross-owner denial. This uses test identities; no upload to a real user's account bypassed CLI consent.

Screenshots (local ignored verification artifacts):

- `output/architecture-sample-overview.png`
- `output/architecture-sample-detail.png`

## Checks

- Focused runtime/export/hierarchy/coverage/planner/backend contract and CLI consent/upload tests: **104 passed**.
- Existing repository-reader/world tests: **20 passed**.
- Actual PostgreSQL investigation and authorization tests: **24 passed**.
- Browser/model checks with actual sample and Wizard exports: **9 passed**, none skipped. Includes bounded projection, deterministic cycle layout, orthogonal paths, legacy compatibility, PostgreSQL/API identity, action-label separation, cylinder rendering, expansion, source evidence, scrolling, zoom/fit/reset, mobile layout, ownership and homepage navigation.
- Frontend standalone TypeScript check: **passed**.
- Frontend Next production build: **passed**. The existing Next configuration skips build-time lint/type validation; TypeScript was therefore run separately. Existing Browserslist and pytest configuration warnings remain.
- Root diff whitespace check: **passed**.

A transient TypeScript run overlapped the build's generated-type cleanup and failed on missing generated files; the standalone rerun after the build passed. Earlier live provider/context failures were retained as failed/incomplete probes rather than claimed as successful investigations.

## Changed product files

Backend/runtime checkout:

- `backend/architecture.py`: compatible hierarchy/coverage contract and validation.
- `backend/tests/test_architecture_contract.py`, `backend/tests/test_architecture_postgres.py`: contract and persisted graph checks.
- `wizard-runtime-engine/src/wizard_kernel/contracts/verification.py`: semantic synthesis schema.
- `wizard-runtime-engine/src/wizard_kernel/control/architecture_coverage.py`: balanced discovery, evidence excerpts, import resolution and bounded context.
- `wizard-runtime-engine/src/wizard_kernel/control/architecture_hierarchy.py`: hierarchy adapter and measured coverage.
- `wizard-runtime-engine/src/wizard_kernel/control/verification.py`: synthesis integration and completion correctness.
- `wizard-runtime-engine/src/wizard_kernel/ports/model.py`, `ports/prompts.py`: existing provider context handling and architectural synthesis guidance.
- `wizard-runtime-engine/src/wizard_kernel/session/architecture.py`: hierarchy export and supported action labels.
- `wizard-runtime-engine/src/wizard_kernel/world/tools.py`: partial-read metadata.
- `wizard-runtime-engine/tests/test_architecture_coverage.py`, `test_architecture_export.py`, `test_architecture_hierarchy.py`, `test_architecture_plan_grounding.py`: regression checks.
- `wizard/cli/display/architecture.py`, `wizard/cli/tui/app.py`: accurate subsystem/consent summary.
- This report.

Website checkout, `wizardsite/`:

- `components/architecture-model.ts`: hierarchy projection, aggregation, pagination and deterministic layout.
- `components/architecture-viewer.tsx`: progressive viewer, functional labels, navigation and evidence.
- `components/architecture.module.css`: shapes, scroll container and responsive explorer.
- `tests/browser/architecture-model.spec.ts`, `tests/browser/architecture.spec.ts`: model and persisted browser checks.

## Remaining limits

The real Wizard investigation remains incomplete: its package/configuration boundary evidence did not satisfy all findings within the current investigation budget. Twenty inspected source files remain unassigned in that export, including some backend migration/configuration, planner/provider and runtime/CLI entry-point evidence. They are accessible as source evidence rather than silently promoted into unsupported subsystems. No additional independent large open-source repository was investigated.

The scanner retains its existing exclusions and depth-eight limit. Read budgets, partial excerpts, unresolvable/dynamic imports and provider reasoning can leave subsystems or runtime behavior unverified. Membership propagated through imports is explicitly an architectural inference. Static imports alone do not justify labels such as `refreshes data` or `stores result`; these require supporting evidence.

The existing graph limits (500 nodes, 2,000 relationships, 3,000 evidence records and 2 MB upload) still apply. Paging reduces rendered detail; it does not eliminate the bounded whole-document fetch or guarantee exhaustive discovery in very large repositories. Older saved investigations receive compatible presentation but must be reinvestigated locally to obtain new semantic hierarchy and measured coverage.
