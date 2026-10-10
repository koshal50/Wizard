# Scoped report examples

These are read-only re-renderings of real saved investigation state with schema 2, not new investigation runs. Original observations, goal states, trust scores and report artifacts were not changed. Older uncited model narratives are excluded by the new citation contract.

| Example | Original investigation | Preserved state |
| --- | --- | --- |
| [Architecture](architecture.md) | inv_be1bb3270a60 | completed |
| [API](api.md) | inv_a5cd5c00a2fa | incomplete |
| [Incomplete runtime verification](incomplete-runtime.md) | inv_17a9b849de49 | incomplete |

The API example can describe only inspected routes; it does not invent the contents of imported routers. Its historical Runtime/web goal results remain in the shared footer. The runtime example preserves the difference between its satisfied goal and the investigation's incomplete Verifier outcome; missing HTTP readiness is explicit.

`regenerate.py` takes a data root and three investigation IDs. It restores models and renders Markdown without making model calls, executing tools, or overwriting saved investigations. Native Markdown `<details>` sections provide expandable evidence, failures, cleanup and graph information in viewers that support them.
