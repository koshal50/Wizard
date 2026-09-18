# Agentic Browser — Architecture (design-only)

A **hybrid agentic browser** for Wizard: the *watchable, co-drivable live browser* of a
v0.app-style preview pane, fused with the *real perceive→decide→act browsing* of an agentic
browser — **without building a browser**. We drive a real engine (Chromium via Playwright)
that already exists, stream its pixels to a page you can watch and grab the wheel on, and
route every action through the kernel we already built.

This document separates, explicitly:

- **REUSE** — what we take from the open-source world and from Wizard's own spine, and do
  **not** rebuild.
- **BUILD** — the minimum net-new code, with exact insertion points (the same surgical
  precision as the Context Engine's "3 edits to wire").

> Convention: design-only, no code yet — same as how the Context Engine was speced.

---

## 0. The one realization everything rests on

**Wizard's investigation loop is already a perceive→decide→act agent loop.** Look at
`control/loop.py`:

```
pick ready node → build_context("explorer", …) → Explorer returns a ToolRequest
   → validate → execute tool → immutable Observation → extractors → EvidenceEngine → KG
   → budget.consume() → repeat
```

That is *exactly* the shape of a browsing agent: observe the page, decide the next action,
act, observe the result. So we do **not** import a browser-agent framework that brings its
own loop (browser-use, an MCP agent runner, Operator-style controllers). Doing so would
smuggle in a second, hidden loop whose actions are invisible to our Observations, whose
budget we don't control, and whose decisions bypass the Context Engine — breaking invariants
1, 3, 5, and 7 at once.

**Instead: a browser action is just another tool.** `read_file` reads a file into an
Observation; `browser_click` clicks a button into an Observation. The page's current state
(its accessibility tree / visible text) flows to the Explorer as a Context Engine section,
*exactly* the way file contents flow today. The Explorer picks the next `browser_*` action.
The kernel executes it. The browser-specific meaning lives entirely in the **tool + extractor
layer** (`world/`, `belief/`) — the control core stays technology-agnostic (invariant 5).

This single decision is what lets us reuse ~90% of what already exists and build very little.

---

## 1. Two planes (the second key idea)

A live browser produces two completely different kinds of data. Conflating them is the
classic mistake. We keep them on separate planes:

| Plane | Carries | Frequency | Transport | Stored? |
|-------|---------|-----------|-----------|---------|
| **Control / narration** | discrete facts — `browser.navigated{url,title}`, `browser.acted{action}`, `browser.extracted{n_claims}` | one per action | **existing `EventBus`** (`session/events.py`) | yes — seq'd history, polled by CLI/TUI |
| **Pixel** | CDP screencast frames out + human mouse/keyboard in | ~10–30 fps | **new WebSocket** `/screencast` | **no — ephemeral**, never touches history |

The narration plane reuses the EventBus untouched (just new event-name constants). The pixel
plane is a dedicated WebSocket that **must not** flow through `EventBus._history` — that list
is kept forever for polling, and 30 fps of JPEG frames would blow memory and pollute the
audit trail. Frames are fire-and-forget.

This split is *why* the EventBus design doesn't need to change: it was built for discrete
lifecycle events, and that's all we put on it. The agent's *decision* events (§2) ride this
same narration plane.

---

## 2. Watching the agent — the interface is a renderer

Everything the agent does is **already** leaving the kernel on the two planes of §1. So "let
me watch it act and make decisions" is **not** a new capability bolted onto the engine — it
is a **renderer of streams that already exist**. This mirrors the Context Engine exactly: a
read-only projection, never a new authority. No watch surface — CLI, editor, or browser — can
admit a claim, move trust, or add a node; those stay kernel-only (invariant 3). "Seeing it"
and "not letting the viewer corrupt it" are the same property.

**What a surface can show is decided purely by which plane the data lives on:**

| The agent's… | Is | Renderable in |
|---|---|---|
| decisions & reasoning — which agent was consulted, the chosen tool + its `reason`, accepted/rejected + why, claim admitted, goal advanced | **text** (narration → `/events`) | **every** surface — CLI, TUI, web, VS Code |
| what it *perceives* — the accessibility snapshot ("sees: `[button: Sign in]`, `[link: Docs]`") | **text** | every surface |
| the live browser **picture** | **pixels** (`/screencast`) | only pixel-capable surfaces — a web page, a VS Code webview (a plain terminal cannot) |

So the terminal isn't a lesser view of *decisions* — text carries the entire reasoning and
perception trace. Pixels are the *only* thing that needs a richer surface.

**Build the streams once, then render cheapest-first:**

| Surface | Shows | Effort | Notes |
|---------|-------|--------|-------|
| **CLI / TUI** (`wizard/cli/tui/`, already built) | full decision + reasoning + perception trace, as text | **small** — mostly *emit the events the renderer already expects* (B8) | `runtime_client/client.py:128` **already** has an `agent.consulted` render branch waiting for a producer |
| **Web live-view** (B6) | everything — `<canvas>` pixels + decision sidebar + optional take-over | medium | the one surface that shows pixels; also the *safest* place to render them (below) |
| **VS Code** | same as web, embedded in the editor | most | a thin extension whose webview loads the **same** `browser.html` — do **not** build a second renderer |

### 2.1 The missing half: emit the *decisions*, not just the outcomes

Today `control/loop.py` emits *results* — `ClaimAdmitted`, `GoalSatisfied`, `NodeFailed` — but
never the decision that produced them. The data already exists (`ToolRequest.reason` in
`contracts/agent.py`; `validation.reason` at `loop.py:404`), and the CLI **already renders**
`agent.consulted` (`client.py:128`) — the *producer* simply never fires. Closing that gap is
**B8**, and it is **not browser-specific**: it lights up the decision trace for the ordinary
file-investigation flow too, turning a stream of "claim admitted" into a legible

> consulted Explorer → chose `browser_navigate(docs)` *because "confirm the deploy target"* →
> validator accepted → observed page → found `LINK` → goal *Verify Deployment* advanced.

### 2.2 Why watching it this way is *safer*, not just visible

The instinct to want it "somewhere safer" is right, and the two-plane split is what delivers
the safety:

- **Pixels are images, not a live site.** Rendering screencast frames onto a `<canvas>` means
  the target page's HTML/JS **never executes in the human's browser** — unlike embedding the
  site in an `<iframe>`. Untrusted pages are watched safely because you receive pictures of
  them, not the pages themselves.
- **The agent's Chromium stays in the egress-limited sandbox** (§6). Only pixels + text cross
  the boundary *outward*; the human's machine never navigates to the target site at all.
- **Watch surfaces are observe-only.** They consume `/events` (poll) and `/screencast`
  (frames). The single thing a surface can send *back* is co-drive input — and that is gated
  behind an explicit "take over" toggle and can be disabled entirely. A fully compromised
  viewer still cannot corrupt the investigation's truth (invariant 3).

That last point is the crux: because the interface is a pure projection, "let me see more" and
"keep it safe" never trade off against each other.

---

## 3. REUSE — open-source (do NOT rebuild)

Licenses are as researched (Aug 2026); re-confirm at adoption time — especially any SSPL
component.

| Component | License | What we use it for | Why not build it |
|-----------|---------|--------------------|------------------|
| **Playwright (Python)** | Apache-2.0 | **The driver.** Atomic actions (`goto`/`click`/`fill`/`go_back`), **accessibility-tree / ARIA snapshot** (`page.accessibility.snapshot()`, `locator.aria_snapshot()`), and **raw CDP access** (`context.new_cdp_session(page)`) for screencast + input. | A browser automation engine is millions of lines. This is the single core new dependency. |
| **Playwright Chromium image** (`mcr.microsoft.com/playwright:*-jammy`) | (image) | Base image for the browser sandbox profile — Chromium + every OS lib preinstalled. | Don't hand-build a Chromium+deps image; it's a solved, maintained artifact. |
| **vLLM + open-weights text model** (Qwen2.5 / DeepSeek / Llama-class) | Apache-2.0 / permissive | The **decision brain** over the **accessibility-tree path → no vision model needed**. Satisfies the zero-budget constraint. Same vLLM endpoint already planned for Yash's planner and the n8n agents. | The Explorer already calls an LLM; browsing just adds page text to its context. |
| **Playwright MCP** (Microsoft) *(optional / reference)* | Apache-2.0 | Reference for the action set + accessibility-snapshot schema ("no vision models needed"). Lift the *contract shapes*, not the runner. | Its agent loop duplicates ours — see §0. Keep as reference to avoid a heavy dep. |
| **browser-use** *(optional / reference)* | MIT | Same: proven DOM-indexing + action vocabulary; local-model friendly. | Same reason — we don't want its embedded loop. |
| **Steel** (`steel-dev/steel-browser`) *(optional backend)* | Apache-2.0 | Drop-in **session backend** with a prebuilt session viewer + cookie/storage persistence, exposed over CDP. Selected via `browser_backend="steel"`. | Only if/when we want managed sessions at scale; **not required for v1**. Apache-2.0 = license-clean. |
| **browserless** *(optional backend)* | **SSPL-1.0 ⚠** | Same role as Steel (CDP + debug viewer). | Prefer Steel; **flag the SSPL obligation** before any hosted use. |
| **UI-TARS-1.5-7B** (ByteDance) *(optional, vision path)* | Apache-2.0 | Open-weights **VLM** for pixel-grounding if a site defeats the DOM path. | Deferred — only needed if accessibility snapshots prove insufficient on real targets. |

**Net new third-party dependency for v1: one — `playwright`.** The WebSocket server is
already covered (see §4, B4).

---

## 4. REUSE — Wizard's own spine (already built, files named)

Everything below already exists and is reused **as-is** except where a small, additive edit
is noted. This is the bulk of the system.

| Kernel piece | File | Role in the browser subsystem | Change |
|--------------|------|-------------------------------|--------|
| `ToolExecutor` | `world/tools.py` | Dispatch host — `browser_*` become new `_tool_*` methods alongside `read_file` etc. | **additive** |
| `ToolRequestValidator` | `control/tool_validator.py` | Deterministic gate before any browser action hits the engine | **additive** (URL allowlist) |
| Docker sandbox | `world/sandbox/docker.py` | Isolation model to clone into a **browser profile** (§6) | reuse pattern |
| `ObservationStore` + `Observation` | `reality/observations.py`, `contracts/observation.py` | Every browser action → one **immutable** Observation (invariant 1) | **additive** (obs types) |
| Belief pipeline | `belief/evidence.py`, `belief/extractors.py`, `belief/knowledge_graph.py`, `belief/trust.py` | Claims extracted from page content, admitted **only** via EvidenceEngine (invariant 2); trust moves kernel-side | **additive** (page extractors) |
| **Context Engine** | `context/` | Projects page state to the Explorer as **trust-stripped** sections (invariant 3) | additive section |
| `EventBus` | `session/events.py` | **Narration plane** (§1) — browser events **and** decision events (§2) | **additive** (event names) |
| FastAPI app + `uvicorn[standard]` | `api/app.py`, `pyproject.toml` | Hosts the new WebSocket. **`uvicorn[standard]` already bundles `websockets`** → no new server dep | reuse |
| CLI / TUI renderer | `wizard/cli/runtime_client/client.py`, `wizard/cli/tui/` | Renders the narration + decision trace (already streams events; `agent.consulted` branch present) | **additive** (B8 branches) |
| The loop | `control/loop.py` | The perceive→decide→act loop itself; `_safe_execute` (invariant 4); `budget.consume()` (invariant 7) | reuse |
| Explorer port (n8n) | `ports/agents.py` | Already decides `ToolRequest`s — now it can decide `browser_*` ones | reuse |
| Sandbox factory | `world/sandbox/__init__.py` | Pattern for a parallel `get_browser()` factory | reuse pattern |

---

## 5. BUILD — the minimum net-new (with insertion points)

Eight small pieces — **B1–B7** for the browser, plus **B8** (decision narration), which is
not browser-specific but is what makes the agent *watchable* everywhere. Each names the exact
file and anchor, mirroring the Context Engine README's "edits to wire" style.

### B1 — `browser_*` tool contracts
- **`world/tools.py`** — add to `_REGISTERED_TOOLS` (currently lines 9–13):
  `browser_navigate`, `browser_snapshot`, `browser_click`, `browser_type`,
  `browser_extract`, `browser_back`. Add matching `_tool_browser_*` methods that delegate to
  the `BrowserRuntime` (B2) and return the standard `{ok, data, error, meta}` envelope.
- **`control/tool_validator.py`** — add the same names to `_ALLOWED_TOOLS` (lines 35–39);
  add a `_URL_TOOLS = {"browser_navigate"}` set and a `_validate_url()` that enforces an
  **allowlist of domains** (the direct analog of the existing `_validate_path` traversal
  guard at lines 100–123 — this is the new egress guard); add structural rules in
  `_validate_structure` (line 125): `browser_click`/`browser_type` require a `selector: str`,
  `browser_type` also `text: str`, `browser_navigate` requires `url: str`.

### B2 — `BrowserRuntime` (Playwright lifecycle)
- **new `world/browser.py`** — `BrowserRuntime` owns one Playwright `browser` → `context` →
  `page` **per investigation** (invariant 6). Methods mirror the tool set (navigate / snapshot
  / click / type / extract / back) and one accessor: `cdp_session()` returning
  `context.new_cdp_session(page)` for the pixel plane. Started/stopped next to `sandbox` in
  the loop (`loop.py` lines 100–108, beside `get_sandbox` / `ToolExecutor`). The
  `ToolExecutor` gets an optional `browser=` handle so `_tool_browser_*` can reach it.

### B3 — browser Observations + extractors
- **`contracts/observation.py`** — extend the `ObsType` Literal (lines 5–8) with
  `"page_content"` and `"browser_action"`.
- **`control/loop.py`** — extend `_TOOL_TO_OBS_TYPE` so `browser_snapshot`/`browser_extract`
  → `page_content` and the action tools → `browser_action`.
- **`belief/extractors.py`** — add page-content extractors that turn a snapshot into claims
  (e.g. `PAGE_TITLE`, `HTTP_STATUS`, `LINK`, domain-specific facts) — **same shape** as the
  existing file extractors, so the EvidenceEngine/trust path is untouched.

### B4 — pixel plane: screencast WebSocket + input
- **new `api/routes_browser.py`** — `@router.websocket("/v1/investigations/{id}/screencast")`.
  On connect: look up that investigation's `BrowserRuntime`, `cdp.send("Page.startScreencast",
  …)`, relay each `Page.screencastFrame` (base64 JPEG) out to the client and
  `Page.screencastFrameAck` back; accept inbound input messages and translate to
  `Input.dispatchMouseEvent` / `Input.dispatchKeyEvent` (this is the **co-drive / take-over**).
- **`api/app.py`** — `app.include_router(routes_browser.router)` (beside line 33–34).
- **No new dependency** — `uvicorn[standard]` already ships `websockets`.

### B5 — narration plane (reuse EventBus)
- **`session/events.py`** — add constants near lines 20–31:
  `BrowserNavigated="browser.navigated"`, `BrowserActed="browser.acted"`,
  `BrowserExtracted="browser.extracted"`. The loop `bus.emit(...)`s them beside the existing
  emits. **No structural change** — CLI/TUI polling via `/events` picks them up for free.

### B6 — thin web live-view front-end (the one net-new UI surface)
- **new static page** served by FastAPI (`api/static/browser.html` + a small route). A
  `<canvas>` draws frames from the `/screencast` WebSocket; it forwards mouse/keyboard for
  take-over (behind an explicit toggle, §2.2); a sidebar renders the narration + decision
  trace polled from the existing `/events`. This exists **because the terminal TUI cannot
  render pixels** — it is the only genuinely new interface surface, and the VS Code webview
  later loads this same page rather than a second renderer.

### B7 — options + factory
- **`contracts/request.py`** — extend `InvestigationOptions` (lines 5–10):
  `browser_enabled: bool = False`, `browser_backend: Literal["container","steel","cdp_url"] =
  "container"`, `browser_cdp_url: str | None = None`, `allowed_domains: list[str] = []`.
- **fold into `world/browser.py`** a `get_browser(options)` factory mirroring `get_sandbox`
  (`world/sandbox/__init__.py`): `"container"` → Playwright-in-browser-profile-container (default);
  `"steel"` / `"cdp_url"` → bind to an external CDP endpoint (reuse Steel's viewer/persistence).

### B8 — decision narration (see the agent think — *not* browser-specific)
This is the piece that answers "let me watch it make decisions," and it pays off for the
existing file-investigation flow immediately — independent of any browser work.
- **`session/events.py`** — add `AgentDecided="agent.decided"`. (`AgentConsulted="agent.consulted"`
  and `ToolRejected="tool.rejected"` **already exist** at lines 30–31, currently unused.)
- **`control/loop.py`** — beside the existing emits: fire `agent.consulted` when the
  Explorer/Verifier is called; fire `agent.decided {tool, reason}` from the chosen
  `ToolRequest.tool` + `.reason` (already captured); fire `tool.rejected {tool, reason}` on
  validator rejection using `validation.reason` (already computed at `loop.py:404`). All
  additive — no new data is invented, it's just published.
- **`wizard/cli/runtime_client/client.py` + `wizard/cli/tui/`** — `client.py:128` already
  handles `agent.consulted`; add `agent.decided` / `tool.rejected` branches and a TUI activity
  line. Result: the terminal shows the full consult → choose → accept/reject → observe → find
  trace with **no pixels required**.

That is the entire build. Everything else is reuse.

---

## 6. The sandbox boundary (the real tension) + security scoping

**The current Docker sandbox cannot run a browser as-is.** `world/sandbox/docker.py` starts
the container with `--network none --read-only -v …:/workspace:ro` (lines 84–104). A browser
needs **network egress** and **writable scratch** — the two things that profile forbids. So
the browser does **not** run in the code-analysis sandbox. It gets a **sibling profile**:

| | Code sandbox (today) | **Browser sandbox profile (new)** |
|---|---|---|
| Network | `--network none` | **egress required** — constrain to `allowed_domains` (proxy/firewall), never wide-open |
| Filesystem | `--read-only`, repo `:ro` | Chromium needs writable `--tmpfs`; **no repo mount** (the browser has no business reading the repo) |
| Image | `python:3.12-slim` | `mcr.microsoft.com/playwright:*-jammy` |
| Lifetime | per investigation | per investigation (invariant 6) |

The egress is the entire new attack surface, and it lands in exactly one deterministic place:
the validator's **URL allowlist** (B1) — the same architectural role the path-traversal guard
already plays for files.

**Security scoping — disposable sessions first.** v1 uses **fresh, disposable, unauthenticated**
browser sessions per investigation: no saved cookies, no real logins, torn down at the end. This
sidesteps the two hard problems of persistent agentic browsers — credential custody and
high-consequence prompt injection (a malicious page telling the agent to act as the logged-in
user). Persistent real-user auth (and, with it, Steel-style session persistence) is a **later,
opt-in** capability, gated behind an explicit decision — not v1.

---

## 7. Data flow (invariants preserved end-to-end)

```mermaid
sequenceDiagram
    participant Loop as control/loop.py
    participant CE as ContextEngine
    participant Ex as Explorer (n8n + vLLM)
    participant V as ToolRequestValidator
    participant TE as ToolExecutor
    participant BR as BrowserRuntime (Playwright)
    participant OS as ObservationStore
    participant EV as EvidenceEngine→KG
    participant Bus as EventBus (narration)
    participant WS as /screencast WS (pixels)

    Loop->>CE: build_context("explorer", …)  %% page state = a trust-stripped section
    CE-->>Loop: packet (no trust, no graph)
    Loop->>Ex: explorer.request(packet)
    Loop->>Bus: emit("agent.consulted", …)  %% B8 — narration plane
    Ex-->>Loop: ToolRequest{browser_click, {selector}, reason}
    Loop->>Bus: emit("agent.decided", {tool, reason})  %% B8
    Loop->>V: validate (allowlist + URL guard + dedup)
    V-->>Loop: valid → sanitised params  (else emit tool.rejected, fallback to node.action)
    Loop->>TE: execute(browser_click)
    TE->>BR: click(selector) via Playwright
    BR-->>TE: {ok, data:{snapshot,…}, error, meta}
    TE-->>Loop: payload
    Loop->>OS: append(obs_type="browser_action")  %% invariant 1
    Loop->>EV: extractors → admit  %% invariant 2, trust kernel-side
    Loop->>Bus: emit("browser.acted", …)  %% narration plane
    par pixel plane (independent, ephemeral)
        BR-->>WS: Page.screencastFrame → canvas
        WS-->>BR: mouse/key → Input.dispatch*  %% human take-over
    end
    Note over Loop: budget.consume() — invariant 7
```

Both planes feed the watch surfaces of §2: the `Bus` events (consult / decide / act / reject)
are polled via `/events` and render in **any** surface; the `WS` frames render only where a
canvas exists.

**Invariant-by-invariant:**

1. **Observations immutable** — each browser action → one frozen `Observation` (reuse
   `obs_store.append`). A screencast frame is *not* an Observation; it's ephemeral pixels.
2. **Claims only via EvidenceEngine** — page-content extractors feed `ev_engine.admit`
   exactly like file extractors; the browser never writes the KG.
3. **Agents never see/write trust or graphs** — the Explorer sees the page as a Context
   Engine section (trust-stripped); it returns a `browser_*` `ToolRequest` and nothing else.
   Watch surfaces are read-only projections and cannot write state either (§2).
4. **Tool failures → Observations, never crashes** — `_safe_execute` already wraps every tool
   (`loop.py` 505–510); a nav timeout / 404 / detached element becomes an error payload →
   Observation.
5. **No technology-specific meaning in core** — the control loop only sees "a tool returned a
   payload." All browser meaning is in `world/browser.py` + `belief/extractors.py`.
6. **Investigations never share state** — one `BrowserRuntime` (one Chromium context, or one
   external session) per investigation; the `/screencast` socket is keyed by investigation id.
7. **Budget always terminates** — a browser action is a node; `budget.consume()` runs after
   it like any other. No hidden sub-loop spends unbudgeted steps (that's the whole point of §0).

---

## 8. Perception: why the DOM path fits the zero-budget constraint

Two ways to perceive a page:

- **Accessibility-tree / DOM (default).** `page.accessibility.snapshot()` yields structured,
  labeled elements as **text**. Any text LLM on vLLM can read it and choose the next action —
  **no vision model, no GPU-hungry VLM.** This is what "no vision models needed" means in
  Playwright MCP / browser-use, and it's the correct default for Wizard's budget.
- **Vision / pixel-grounding (optional).** If a site is canvas-heavy or defeats the DOM path,
  swap in **UI-TARS-1.5-7B** (open-weights, Apache-2.0) on the same vLLM. Deferred until a real
  target proves the DOM path insufficient (YAGNI).

Note the pixel plane (§1) is for the **human** to watch and co-drive — it is **not** the
agent's perception channel. The agent perceives via the accessibility snapshot (which is also
the text a terminal surface shows under "what it sees", §2). Keeping those two separate is what
lets the brain stay a cheap text model while the human still gets a live picture.

---

## 9. Build order & status

| # | Piece | Depends on | State |
|---|-------|-----------|-------|
| B8 | decision narration (`agent.decided` / `tool.rejected`) — lights up the TUI; **not** browser-specific | — | **design** |
| B2 | `BrowserRuntime` + `playwright` dep | — | **design** |
| B1 | `browser_*` tools + validator URL guard | B2 | **design** |
| B3 | browser Observations + page extractors | B1 | **design** |
| B7 | options + `get_browser` factory | B2 | **design** |
| B5 | narration event names (`browser.*`) | B1 | **design** |
| B4 | `/screencast` WebSocket + input | B2 | **design** |
| B6 | web live-view front-end | B4, B5 | **design** |
| — | browser sandbox profile (egress + Playwright image) | B2 | **design** |
| — | VS Code webview (loads B6's page verbatim) | B6 | **future** |

Milestones, cheapest-first:

1. **B8 alone** — emit the decision events and your *existing* TUI shows the agent consulting,
   choosing (with its reason), and finding — as text, no browser at all. Immediately improves
   the file-investigation flow too.
2. **B1+B2+B3 headless** — real agentic browsing (navigate + extract claims from live pages)
   through the existing loop, fully invariant-clean, still no UI.
3. **B4+B6** — layer the v0.app-style live pixels + watch-and-take-over on top.
4. **VS Code** — last; a thin extension that reuses B6's page.

---

## 10. Open decisions (genuine forks, not yet chosen)

1. **Browser location for v1** — self-managed Playwright-in-container (invariant-6 clean,
   one dep, default) vs. external **Steel** from day one (prebuilt viewer + persistence, but a
   service to run and a boundary outside the per-investigation container). Recommendation:
   **container default**, Steel as an opt-in `browser_backend`.
2. **Egress enforcement** — validator allowlist only, or allowlist **plus** a container-level
   egress proxy/firewall (defense in depth). Recommendation: **both** before any non-disposable
   use.
3. **When (if ever) to add persistent auth** — deferred; needs its own threat model for
   credential custody + prompt-injection before it ships.

---

Files this touches (all additive): `world/tools.py` · `control/tool_validator.py` ·
new `world/browser.py` · `contracts/observation.py` · `belief/extractors.py` ·
`session/events.py` · `control/loop.py` (new emits) · new `api/routes_browser.py` · `api/app.py` ·
`contracts/request.py` · new `api/static/browser.html` · new browser sandbox profile beside
`world/sandbox/docker.py`. Decision narration (B8) also touches the CLI renderer
`wizard/cli/runtime_client/client.py` + `wizard/cli/tui/`. New dependency: `playwright`.
No change to the 7 invariants, the control core, or any existing port contract.
