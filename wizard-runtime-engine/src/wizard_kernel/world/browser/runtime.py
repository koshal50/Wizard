"""BrowserRuntime — a real Chromium engine (Playwright) driven as a Wizard tool.

Design (see agentic-browser-architecture.md §0, §1):

- A browser action is *just another tool*. This class owns ONE Playwright
  browser -> context -> page per investigation (invariant 6) and exposes
  synchronous action methods (navigate / snapshot / click / fill / back /
  extract) that the kernel's synchronous ToolExecutor calls exactly like
  ``read_file``.
- Playwright's async API is the modern engine, but the kernel loop is
  synchronous while the ``/screencast`` WebSocket is asynchronous, and BOTH must
  reach the SAME live page. So the runtime owns a dedicated asyncio event loop on
  its own thread and is the single owner of every Playwright object; callers
  marshal onto that loop via ``run_coroutine_threadsafe``. This is the minimum
  that lets a sync loop drive the page while an async socket streams its pixels.
- ``playwright`` is imported lazily, so the kernel never depends on it unless a
  browser-enabled investigation actually starts one (keeps existing installs and
  imports untouched).

Invariant 4: action failures (nav timeout, missing element, HTTP error) surface
as data or raise and are caught at the tool layer -> Observation, never a crash.
Invariant 5: no technology-specific meaning leaks into the control core — all of
it lives here and in the extractors.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from typing import Callable

log = logging.getLogger(__name__)


class BrowserRuntime:
    """Owns one Chromium page per investigation. Started/stopped beside the sandbox."""

    def __init__(
        self,
        *,
        backend: str = "local",
        cdp_url: str | None = None,
        headless: bool = True,
        nav_timeout_ms: int = 15000,
        action_timeout_ms: int = 8000,
    ) -> None:
        self._backend = backend
        self._cdp_url = cdp_url
        self._headless = headless
        self._nav_timeout = nav_timeout_ms
        self._action_timeout = action_timeout_ms

        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._pw = None
        self._browser = None
        self._context = None
        self._page = None
        self._cdp = None
        # Screencast: the CDP frame handler is registered ONCE; reconnecting a
        # viewer just swaps this callback, so frames never duplicate or leak a
        # stale closure onto a dead socket's loop.
        self._on_frame: Callable[[str], None] | None = None
        self._screencast_wired = False

    # ── lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Spin up the dedicated loop thread and open the page. Blocks until ready."""
        ready = threading.Event()
        boot_error: dict[str, BaseException] = {}

        def _runner() -> None:
            loop = asyncio.new_event_loop()
            self._loop = loop
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self._a_start())
            except BaseException as exc:  # noqa: BLE001 — report boot failure to start()
                boot_error["e"] = exc
                ready.set()
                return
            ready.set()
            loop.run_forever()

        self._thread = threading.Thread(target=_runner, name="wizard-browser", daemon=True)
        self._thread.start()
        ready.wait()
        if "e" in boot_error:
            raise RuntimeError(f"browser failed to start: {boot_error['e']}") from boot_error["e"]

    def stop(self) -> None:
        """Close the page/browser and tear down the loop thread. Best-effort."""
        if not self._loop:
            return
        try:
            self._call(self._a_stop(), timeout=20)
        except Exception:  # noqa: BLE001 — teardown never raises to the caller
            log.debug("browser stop error", exc_info=True)
        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=5)
        self._loop = None

    async def _a_start(self) -> None:
        from playwright.async_api import async_playwright  # lazy — opt-in dependency

        self._pw = await async_playwright().start()
        if self._backend == "cdp_url":
            if not self._cdp_url:
                raise ValueError("browser_backend 'cdp_url' requires browser_cdp_url")
            self._browser = await self._pw.chromium.connect_over_cdp(self._cdp_url)
            self._context = (
                self._browser.contexts[0]
                if self._browser.contexts
                else await self._browser.new_context()
            )
        else:  # "local" — launch a Chromium in this environment
            self._browser = await self._pw.chromium.launch(headless=self._headless)
            self._context = await self._browser.new_context()
        self._context.set_default_timeout(self._action_timeout)
        self._page = self._context.pages[0] if self._context.pages else await self._context.new_page()

    async def _a_stop(self) -> None:
        if self._cdp is not None:
            try:
                await self._cdp.detach()
            except Exception:  # noqa: BLE001
                pass
            self._cdp = None
        if self._context is not None:
            await self._context.close()
        if self._browser is not None:
            await self._browser.close()
        if self._pw is not None:
            await self._pw.stop()

    def _call(self, coro, timeout: float | None = None):
        """Run a coroutine on the browser loop from any other thread and block for it."""
        if not self._loop:
            raise RuntimeError("browser not started")
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout=timeout)

    # ── actions (sync — called by ToolExecutor on the loop thread) ─────────────

    def navigate(self, url: str) -> dict:
        return self._call(self._a_navigate(url), timeout=self._nav_timeout / 1000 + 10)

    def snapshot(self) -> dict:
        return self._call(self._a_snapshot(), timeout=self._action_timeout / 1000 + 10)

    def click(self, selector: str) -> dict:
        return self._call(self._a_click(selector), timeout=self._action_timeout / 1000 + 10)

    def fill(self, selector: str, text: str) -> dict:
        return self._call(self._a_fill(selector, text), timeout=self._action_timeout / 1000 + 10)

    def back(self) -> dict:
        return self._call(self._a_back(), timeout=self._nav_timeout / 1000 + 10)

    def extract(self) -> dict:
        return self._call(self._a_extract(), timeout=self._action_timeout / 1000 + 10)

    async def _a_navigate(self, url: str) -> dict:
        resp = await self._page.goto(url, wait_until="domcontentloaded", timeout=self._nav_timeout)
        return {"url": self._page.url, "status": resp.status if resp else None,
                "title": await self._page.title()}

    async def _a_snapshot(self) -> dict:
        # Playwright's ARIA snapshot is the modern accessibility tree (page.accessibility
        # was removed): compact YAML of role + name + state, ideal for a text agent.
        snapshot = await self._page.locator("body").aria_snapshot()
        return {
            "url": self._page.url,
            "title": await self._page.title(),
            "snapshot": snapshot,
            "node_count": sum(1 for ln in snapshot.splitlines() if ln.strip()),
            "links": await self._links(),
        }

    async def _a_click(self, selector: str) -> dict:
        await self._page.click(selector, timeout=self._action_timeout)
        return {"selector": selector, "clicked": True, "url": self._page.url}

    async def _a_fill(self, selector: str, text: str) -> dict:
        await self._page.fill(selector, text, timeout=self._action_timeout)
        return {"selector": selector, "typed": True, "url": self._page.url}

    async def _a_back(self) -> dict:
        resp = await self._page.go_back(wait_until="domcontentloaded", timeout=self._nav_timeout)
        return {"url": self._page.url, "status": resp.status if resp else None,
                "title": await self._page.title()}

    async def _a_extract(self) -> dict:
        try:
            text = await self._page.inner_text("body", timeout=self._action_timeout)
        except Exception:  # noqa: BLE001 — pages without a body still yield url/title/links
            text = ""
        return {"url": self._page.url, "title": await self._page.title(),
                "text": text[:20000], "links": await self._links()}

    async def _links(self) -> list[dict]:
        try:
            return await self._page.eval_on_selector_all(
                "a[href]",
                "els => els.slice(0, 50).map(e => "
                "({text: (e.textContent || '').trim().slice(0, 80), href: e.href}))",
            )
        except Exception:  # noqa: BLE001
            return []

    # ── pixel plane (called by the async /screencast route via to_thread) ──────

    def start_screencast(self, on_frame: Callable[[str], None]) -> None:
        """Begin streaming JPEG frames. ``on_frame`` is invoked from the loop thread."""
        self._call(self._a_start_screencast(on_frame), timeout=10)

    def stop_screencast(self) -> None:
        if self._loop:
            try:
                self._call(self._a_stop_screencast(), timeout=10)
            except Exception:  # noqa: BLE001
                pass

    def send_input(self, msg: dict) -> None:
        """Dispatch a human take-over input event (mouse/key) to the page."""
        self._call(self._a_send_input(msg), timeout=5)

    async def _a_start_screencast(self, on_frame: Callable[[str], None]) -> None:
        self._on_frame = on_frame
        if self._cdp is None:
            self._cdp = await self._context.new_cdp_session(self._page)
        if not self._screencast_wired:
            def _handler(params: dict) -> None:
                cb = self._on_frame  # swappable — None when no viewer is attached
                if cb is not None:
                    cb(params.get("data", ""))
                sid = params.get("sessionId")
                if sid is not None and self._cdp is not None:
                    # ack on the loop so the next frame flows (handler runs on the loop thread)
                    asyncio.ensure_future(
                        self._cdp.send("Page.screencastFrameAck", {"sessionId": sid})
                    )

            self._cdp.on("Page.screencastFrame", _handler)
            self._screencast_wired = True
        await self._cdp.send("Page.startScreencast", {
            "format": "jpeg", "quality": 60, "maxWidth": 1280, "maxHeight": 720, "everyNthFrame": 1,
        })

    async def _a_stop_screencast(self) -> None:
        self._on_frame = None  # detach viewer; handler stays wired and no-ops
        if self._cdp is not None:
            try:
                await self._cdp.send("Page.stopScreencast")
            except Exception:  # noqa: BLE001
                pass

    async def _a_send_input(self, msg: dict) -> None:
        if self._cdp is None:
            return
        kind = msg.get("kind")
        if kind == "mouse":
            await self._cdp.send("Input.dispatchMouseEvent", {
                "type": msg.get("type", "mouseMoved"),
                "x": float(msg.get("x", 0)), "y": float(msg.get("y", 0)),
                "button": msg.get("button", "none"),
                "clickCount": int(msg.get("clickCount", 0)),
            })
        elif kind == "key":
            await self._cdp.send("Input.dispatchKeyEvent", {
                "type": msg.get("type", "char"),
                "text": msg.get("text", ""),
                "key": msg.get("key", ""),
            })
