# Wizard Agentic Browser

A real Chromium engine driven as a Wizard **tool**, so the agent can investigate live web
apps (deployed sites, dashboards, dev servers) with the *same* deterministic runtime that
already investigates files. **Built and verified end-to-end** — 20 unit tests + full suite
(185) green, and a real Chromium exercised live (navigate / snapshot / fill / click / extract
+ a real JPEG screencast frame).

It is **opt-in and additive**: default off, `playwright` is imported lazily, and nothing in
the existing kernel changes behaviour unless an investigation explicitly enables it.

> Core thesis: **a browser action is just another tool.** We reuse Playwright's *actions +
> ARIA snapshot + CDP* — never its agent runner. The kernel's existing perceive→decide→act
> loop stays the one and only loop, so all seven invariants hold unchanged.

---

## 1. What was built

| File | Role |
|------|------|
| `runtime.py` | `BrowserRuntime` — owns one Chromium page per investigation on a dedicated asyncio loop-thread; exposes **sync** action methods the sync `ToolExecutor` calls like `read_file`. |
| `factory.py` | `get_browser(options)` → a `BrowserRuntime` for the chosen backend. |
| `__init__.py` | Per-investigation registry (`register_runtime` / `get_runtime` / `unregister_runtime`) so the screencast route can find the live page. |

Plus these **additive edits** to existing kernel files (all guarded by `browser_enabled`):

| Concern | Where | What |
|---------|-------|------|
| 6 tool contracts | `world/tools.py` | `browser_navigate / snapshot / click / type / back / extract`, each returning the standard `{ok,data,error,meta}` envelope. |
| URL egress guard | `control/tool_validator.py` | Fail-closed allowlist (`allowed_domains`); http/https only; exact-or-subdomain match; browser tools excluded from dedup (the page changes between identical calls). |
| Observations | `contracts/observation.py` | New obs types `browser_action` + `page_content`. |
| Evidence | `belief/extractors.py` | Browser observations → **WEB** claims (`current_url`, `http_status:<url>`, `page_title`, `a11y_node_count`, `link_count`, `has_text_content`). |
| Trust | `belief/trust.py` | `browser_*` → **execution** tier. |
| Narration | `session/events.py` + `control/loop.py` | `browser.navigated` / `browser.acted` / `browser.extracted` events + `agent.decided` / `tool.rejected`. |
| Pixel plane | `api/routes_browser.py` + `api/static/browser.html` | Ephemeral screencast WebSocket + self-contained live-view page. |
| Options | `contracts/request.py` | `browser_enabled`, `browser_backend`, `browser_cdp_url`, `allowed_domains`. |

### The 6 tools

| Tool | Params | Observation | WEB claims produced |
|------|--------|-------------|---------------------|
| `browser_navigate` | `url` | `browser_action` | current_url, http_status, page_title |
| `browser_back` | — | `browser_action` | current_url, http_status, page_title |
| `browser_click` | `selector` | `browser_action` | current_url |
| `browser_type` | `selector`, `text` | `browser_action` | current_url |
| `browser_snapshot` | — | `page_content` | current_url, page_title, a11y_node_count, link_count, has_text_content |
| `browser_extract` | — | `page_content` | current_url, page_title, link_count, has_text_content |

**Perception = the ARIA snapshot** (`page.locator("body").aria_snapshot()`), a compact YAML of
role + name + state (`- link "Docs": /url: …`). It goes to a **text** LLM — no vision model.
(`page.accessibility` was removed in Playwright ≥1.55; do not reintroduce a hand-rolled tree.)

### Two planes (never mixed)

- **Narration** — discrete `browser.*` events on the existing `EventBus` (`/events`). Text, so
  it renders in *every* surface including the plain terminal.
- **Pixels** — CDP `Page.startScreencast` JPEG frames on a **separate** ephemeral WebSocket
  `/v1/investigations/{id}/screencast`. Frames **never** enter `EventBus._history`. Only the
  web page / VS Code webview shows pixels; the terminal is still a full *decision* view.

---

## 2. How a browser action flows through the kernel

```
Planner node (browse intent)
      │
      ▼
Explorer  ──picks──►  ToolRequest{ tool:"browser_navigate", params:{url} }
      │
      ▼
ToolRequestValidator   ← URL egress guard (allowed_domains, fail-closed)
      │ valid
      ▼
ToolExecutor ──► BrowserRuntime (Playwright, own loop-thread) ──► action result
      │
      ▼
Observation (browser_action | page_content)   ← immutable (invariant 1)
      │
      ▼
EvidenceEngine ──► WEB claims ──► KnowledgeGraph (trust: execution tier)
      │                                   │
      ▼                                   ▼
browser.* narration event            Verifier reviews claims (advisory)
```

Every invariant is preserved: intelligence only *proposes* a `ToolRequest`; the deterministic
runtime validates it (URL guard), executes it, and is the sole writer of observations, claims,
and trust. A nav timeout / missing selector / HTTP error becomes an **error Observation**, never
a crash (invariant 4). No web-specific meaning lives in the control core — it's all in this
package + the extractors (invariant 5).

---

## 3. Integrating the agent system

The agents live on other branches and the kernel already has the *ports* to call them
(`ports/agents.py`, `ports/planner.py`):

| Agent | Branch | Service endpoint | Kernel port |
|-------|--------|------------------|-------------|
| Investigation Planner | `yash-code` | `wizard-investigation-planner` (TS, `/plan/*`) | `HttpPlanner` |
| Explorer | `feature/wizard-agents` | `POST /explorer/investigate` (Python) | `HttpExplorer` |
| Verifier | `feature/wizard-agents` | `POST /verification/verify` (Python) | `HttpVerifier` |

> ⚠️ **One seam applies to both agents.** The kernel's ports today speak a *simpler* shape than
> the `wizard_agents` service. `HttpExplorer.request(context)` POSTs a flat context dict and
> expects `ExplorerResponse{ tool_request{ tool:str, parameters, reason } }`, but the service
> expects a structured `ExplorerInput` and returns `ExplorerOutput{ selected_tool: ToolName, … }`
> (same story for Verifier: `assess(claims)` vs `VerificationInput`→`VerificationOutput`). An
> **adapter** must reconcile them. The browser changes below assume that adapter exists (or that
> `HttpExplorer`/`HttpVerifier` are updated to the service contract). This seam is *not*
> browser-specific — it already blocks the file-only flow from using the real agents.

### 3a. Investigation Planner (`yash-code`)

The Planner reasons at the **node-type** level, not raw tool names. Its `nodeActionSchema`
(`src/planner/schemas.ts`) is a tagged union of 8 actions: `discovery, read, execute, parse,
verify, synthesize, planner, checkpoint`. It does **not** — and should not — know Playwright.

To let it plan web steps:

1. **Add a `browse` node action** to `src/planner/schemas.ts` + the `NodeAction` type in
   `src/core/types.ts` + `nodeTypeSchema`:
   ```ts
   const browseAction = object({
     type: enum_(["browse"] as const),
     operation: enum_(["navigate","snapshot","click","type","back","extract"] as const),
     url: string().optional(),      // required for navigate
     selector: string().optional(), // required for click/type
     text: string().optional(),     // required for type
   });
   ```
2. **Update `src/planner/prompts.ts`** so the Planner proposes `browse` nodes when the intent
   involves a running web app / URL / deployed site (e.g. "verify the login page works").
3. **Kernel maps `browse` → concrete tool.** The kernel node's `action` carries `{tool, params}`
   (see `MockExplorer` reading `node_action["tool"]`). So the Planner→kernel bridge translates
   `browse.operation` → `browser_<operation>` and lifts `url`/`selector`/`text` into `params`.
   Nothing else in the Planner needs browser knowledge.

### 3b. Explorer (`feature/wizard-agents`) — most work here

The Explorer chooses the concrete `ToolRequest`. Two required changes + one enhancement:

1. **Add the browser tools to the `ToolName` enum** (`app/contracts/common.py`). This is the
   single source of truth — *Explorer output validation rejects any tool not in the enum*, so
   without this the Explorer can never request one:
   ```python
   class ToolName(str, Enum):
       ...
       BROWSER_NAVIGATE = "browser_navigate"
       BROWSER_SNAPSHOT = "browser_snapshot"
       BROWSER_CLICK    = "browser_click"
       BROWSER_TYPE     = "browser_type"
       BROWSER_BACK     = "browser_back"
       BROWSER_EXTRACT  = "browser_extract"
   ```
2. **Describe them in `TOOL_REGISTRY`** (`app/explorer/tools.py`) so the prompt lists their
   params — e.g. navigate→`["url"]`, click→`["selector"]`, type→`["selector","text"]`,
   snapshot/back/extract→`[]`.
3. **Feed the Explorer the page (enhancement).** The Explorer decides selectors from what it can
   *see*. On the kernel side the AVAILABLE TOOLS section already includes the browser tools
   (`context/packager._available_tools()` emits `_REGISTERED_TOOLS`), and WEB claims (url, title,
   link_count) reach it as claims — but `packager._summarize_obs()` currently collapses a
   `page_content` observation to one line and **drops the ARIA snapshot text**. To drive
   multi-step interaction (which button to click), surface the latest snapshot into the Explorer
   packet — either enrich `_summarize_obs` for `page_content`, or add a dedicated **"CURRENT
   PAGE"** section carrying `data["snapshot"]` (+ url/title). Navigate/extract work without this;
   reliable clicking needs it.

The adapter (see seam above) must forward `available_tools` (kernel already lists them) and map
`ExplorerOutput.selected_tool` → the kernel's `tool_request.tool` string.

### 3c. Verifier (`feature/wizard-agents`) — least work

Browser evidence already lands in the tier the Verifier understands:

- `browser_*` observations are **execution** tier (`belief/trust.py`), which maps directly to
  `EvidenceSource.EXECUTION` in `app/contracts/verification.py`. WEB claims (`current_url`,
  `http_status:<url>`, `page_title`, …) flow in as ordinary `ClaimInput`s with execution
  evidence — **no browser-specific change is required**.
- *Optional:* add `WEB = "web"` to `EvidenceSource` if you want web evidence labelled distinctly
  in `verification_report.md`. `EXECUTION` is already accurate (a live page fetch is execution
  evidence).
- The Verifier's `recommended_additional_investigations` can suggest more browsing ("navigate to
  `/admin` to confirm the auth claim"); the runtime independently turns those into new Planner
  nodes — the Verifier stays advisory (invariant 3).

---

## 4. Integrating the CLI (`wizard/cli/runtime_client/client.py` owner)

The CLI already POSTs to `/v1/investigations` and polls `/events`. Two small additions light up
browsing end-to-end (kept out of this branch — it's yours to own):

**1. Pass the browser options** in the request `options` payload (add flags such as `--browser`,
`--browser-backend`, `--allow-domain`):

```python
"options": {
    ...,
    "browser_enabled": True,             # default False
    "browser_backend": "local",          # "local" | "cdp_url" | "container"
    "browser_cdp_url": None,             # required when backend == "cdp_url"
    "allowed_domains": ["example.com"],  # FAIL-CLOSED: empty ⇒ all navigation blocked
}
```

> ⚠️ `allowed_domains` is **fail-closed**. Leave it empty and *every* navigation is rejected by
> the URL guard by design. The CLI must collect the domains the user authorises.

**2. Render the new events** in the existing `/events` poll loop (payload fields shown):

```python
elif ev_type == "agent.decided":      # {node_id, source, tool, reason}
    console.print(f"[blue]▸[/blue] Decided: [bold]{payload.get('tool')}[/bold] — {payload.get('reason','')}")
elif ev_type == "tool.rejected":      # {node_id, tool, reason}
    console.print(f"[yellow]⊘[/yellow] Rejected [bold]{payload.get('tool')}[/bold]: {payload.get('reason')}")
elif ev_type == "browser.navigated":  # {url, status, title}
    console.print(f"[green]🌐[/green] {payload.get('title') or payload.get('url')} [dim](HTTP {payload.get('status')})[/dim]")
elif ev_type == "browser.acted":      # {tool, url, selector}
    console.print(f"  [magenta]🖱[/magenta] {payload.get('tool')} [dim]{payload.get('selector') or ''}[/dim]")
elif ev_type == "browser.extracted":  # {url, title, node_count, link_count}
    console.print(f"  [cyan]📄[/cyan] {payload.get('title') or payload.get('url')} [dim]({payload.get('node_count')} nodes · {payload.get('link_count')} links)[/dim]")
```

**3. Watch the live picture (optional).** The full text narration above is enough in a terminal.
To *see* the browser, open the live-view page in any browser or a VS Code webview:

```
http://127.0.0.1:8080/v1/investigations/{investigation_id}/live
```

It polls `/events` (left, text) and connects the screencast WebSocket (right, pixels), with an
opt-in **"Take over"** toggle for human co-drive. Frames are drawn as images, so the target
page's JS never runs in the viewer's browser.

---

## 5. Backends & dependency

- **`local`** (default) — launches Chromium in this environment. Needs `pip install
  "wizard-kernel[browser]"` then `python -m playwright install chromium`.
- **`cdp_url`** — connects to an external Chromium over CDP (`browser_cdp_url`), e.g. a remote
  browser service. No local browser needed.
- **`container`** — deferred; currently falls back to `local` with a warning. A network-egress
  browser-sandbox profile is future work (the current file sandbox is `--network none`).

`playwright` is the **only** new dependency (optional extra `browser`), imported lazily inside
`BrowserRuntime._a_start`. `uvicorn[standard]` already bundles `websockets`, so the screencast
endpoint needs no new server dependency.

---

## 6. Verified

`pytest tests/test_browser.py` → 20 passed (incl. a live-Chromium smoke test, auto-skipped when
no browser binary is present). Full suite: 185 passed. Real browser confirmed end-to-end:
navigate, ARIA snapshot, fill, click (page JS actually ran), extract, and a real 8577-byte JPEG
screencast frame across the sync→async→CDP bridge.
