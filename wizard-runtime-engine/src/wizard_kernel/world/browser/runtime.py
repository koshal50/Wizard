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
        allowed_domains: list[str] | None = None,
    ) -> None:
        self._backend = backend
        self._cdp_url = cdp_url
        self._headless = headless
        self._nav_timeout = nav_timeout_ms
        self._action_timeout = action_timeout_ms
        # Fail-closed, like the tool validator's policy of the same name: an empty
        # list admits nothing. Enforced on the page's own network layer (see
        # _a_install_egress_guard) so it covers every way out — navigate, a click
        # that follows a link, a form post, a subresource fetch — not only the one
        # tool that happens to take a URL.
        self._allowed = tuple(allowed_domains or ())

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
        await self._a_install_egress_guard()

    # ── egress (the boundary that covers every way out of the page) ────────────

    async def _a_install_egress_guard(self) -> None:
        """Refuse every request to a host the allowlist does not admit.

        The tool validator checks a `browser_navigate` URL before the action runs.
        That check cannot cover a click: nothing knows where a link goes until it
        is followed, and by then the request has already been made. So the guard
        lives where the requests actually are — the page's network layer — and it
        admits by host, fail-closed, exactly like the validator.

        Subresource requests are covered too, which matters more than it sounds: a
        page that pulls a script or a font from a third party has already told
        that third party this run exists. The allowlist is the user's statement of
        who may be contacted, so honouring it for the document but not for its
        images would be a boundary in name only.

        `about:` / `data:` / `blob:` are admitted unconditionally: they are the
        page's own innards (about:blank before a navigation, inline data URIs) and
        reaching no host at all. Everything else is judged by hostname.
        """
        from urllib.parse import urlparse

        async def _guard(route, request) -> None:
            url = request.url
            if url.startswith(("about:", "data:", "blob:")):
                await route.continue_()
                return
            parsed = urlparse(url)
            host = (parsed.hostname or "").lower()
            if parsed.scheme in ("http", "https") and self._host_allowed(host):
                await route.continue_()
                return
            # Aborted, not redirected: a redirect would still be a request this
            # run made to a host the user excluded. The refusal is recorded so the
            # trace can say what was blocked rather than the page silently missing
            # a resource.
            log.info("browser egress blocked %s (allowed=%s)", url, list(self._allowed))
            self._blocked.append(url)
            await route.abort()

        self._blocked: list[str] = []
        await self._context.route("**/*", _guard)

    def _host_allowed(self, host: str) -> bool:
        """Same rule as the tool validator: exact domain, or a subdomain of one."""
        for domain in self._allowed:
            d = domain.lower().lstrip(".")
            if host == d or host.endswith("." + d):
                return True
        return False

    @property
    def blocked_requests(self) -> list[str]:
        """URLs this page tried to reach and the allowlist refused, in order."""
        return list(getattr(self, "_blocked", []))

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

    def page_view(self) -> dict | None:
        """What the page is right now, shaped for a human watching rather than a script.

        Not one of the tools and deliberately not reachable as one: nothing here
        enters an Observation, so nothing here becomes a claim, and no plan step can
        spend budget on it. It is the same split the screencast already makes — the
        pixels a viewer watches are not evidence either — and it exists because the
        two readings want opposite things. A control as the planner needs it carries
        fourteen fields (form action, DOM order, required, href) so a script can be
        written from it; a control as a *pane* needs three, because the pane has
        forty columns and a reader who wants to recognise the button they are
        watching get pressed.

        Best-effort by construction: a page mid-navigation has no controls to read,
        and a viewer is not owed an exception for catching the page at that moment.
        None means "could not read it", and the caller shows what it last had.
        """
        try:
            return self._call(self._a_page_view(), timeout=self._action_timeout / 1000 + 10)
        except Exception:  # noqa: BLE001 — a viewer's read must never fail a run
            return None

    async def _a_navigate(self, url: str) -> dict:
        resp = await self._page.goto(url, wait_until="domcontentloaded", timeout=self._nav_timeout)
        return {"url": self._page.url, "status": resp.status if resp else None,
                "title": await self._page.title()}

    async def _a_snapshot(self) -> dict:
        # Playwright's ARIA snapshot is the modern accessibility tree (page.accessibility
        # was removed): compact YAML of role + name + state, ideal for a text agent.
        snapshot = await self._page.locator("body").aria_snapshot()
        state = await self._page_state()
        return {
            "url": self._page.url,
            "title": await self._page.title(),
            "snapshot": snapshot,
            "node_count": sum(1 for ln in snapshot.splitlines() if ln.strip()),
            "links": await self._links(),
            "controls": await self._controls(),
            **state,
        }

    async def _a_click(self, selector: str) -> dict:
        # The fingerprint is taken BEFORE the click, on this same coroutine, so the
        # "did it change anything" answer compares the page to itself and not to
        # some earlier node's reading of it. Taken here rather than by the caller
        # because the caller is on another thread and the page is only ever read
        # from this one — a second read from outside would race the click.
        name = await self._name_of(selector)
        before = await self._state()
        await self._page.click(selector, timeout=self._action_timeout)
        after = await self._state()
        return {"selector": selector, "selector_name": name, "clicked": True,
                "url": self._page.url,
                "effect": _effect(before, after), "state_before": before, "state_after": after}

    async def _a_fill(self, selector: str, text: str) -> dict:
        # Typing is its own claim: the field either took the value or it did not,
        # and that answer is readable off the element rather than inferred from
        # the absence of an exception. A page whose controlled input rejects the
        # keystroke still raises nothing.
        #
        # The same before/after fingerprint a click takes, for the same reason.
        # A type is not always inert: a controlled input that reformats, a field
        # whose validation message appears, a form that enables its submit button
        # once every field is filled all change the page, and a report that could
        # only say "a value was typed" would read those three and a field wired to
        # nothing identically. Read on this coroutine, like the click's, because
        # the page is only ever read from here.
        name = await self._name_of(selector)
        before = await self._state()
        await self._page.fill(selector, text, timeout=self._action_timeout)
        value = await self._field_value(selector)
        after = await self._state()
        return {"selector": selector, "selector_name": name, "typed": True,
                "url": self._page.url,
                "value": value, "effect": _effect(before, after),
                "state_before": before, "state_after": after}

    async def _name_of(self, selector: str) -> str | None:
        """What the control a selector addresses is called, in the page's own words.

        Looked up in `_controls` rather than read off the element here, so the
        name a viewer is shown is derived by the same rule the planner's script
        was written from. Reading it a second way would be two rules for one
        thing, and the day they disagreed the pane and the script would be
        describing different controls.

        Taken BEFORE the action, which is the only moment it can be. A click that
        navigates, or one whose button renames itself the moment it starts
        working, leaves nothing behind under that selector — and that is exactly
        the case where a viewer most needs the name, because the only other thing
        left to call the control by is its selector.

        Best-effort: a page that cannot be scanned costs a name, not an action.
        """
        if not selector:
            return None
        try:
            for control in await self._controls():
                if control.get("selector") == selector:
                    return control.get("name") or None
        except Exception:  # noqa: BLE001 — an unnamed control is still a pressable one
            return None
        return None

    async def _a_back(self) -> dict:
        resp = await self._page.go_back(wait_until="domcontentloaded", timeout=self._nav_timeout)
        return {"url": self._page.url, "status": resp.status if resp else None,
                "title": await self._page.title()}

    async def _a_extract(self) -> dict:
        try:
            text = await self._page.inner_text("body", timeout=self._action_timeout)
        except Exception:  # noqa: BLE001 — pages without a body still yield url/title/links
            text = ""
        state = await self._page_state()
        return {"url": self._page.url, "title": await self._page.title(),
                "text": text[:20000], "links": await self._links(),
                "controls": await self._controls(), **state}

    async def _a_page_view(self) -> dict:
        """The page as a viewer needs it: where it is, and what can be pressed."""
        state = await self._state()
        return {
            "url": state["url"],
            "title": state["title"],
            "node_count": state["node_count"],
            "controls": [
                {k: c.get(k) for k in _VIEW_CONTROL_KEYS} for c in await self._controls()
            ],
        }

    async def _links(self) -> list[dict]:
        try:
            return await self._page.eval_on_selector_all(
                "a[href]",
                "els => els.slice(0, 50).map(e => "
                "({text: (e.textContent || '').trim().slice(0, 80), href: e.href}))",
            )
        except Exception:  # noqa: BLE001
            return []

    # ── page shape (what the planner writes its script from) ──────────────────

    async def _state(self) -> dict:
        """A cheap fingerprint of what the page currently is.

        Compared before and after an interaction to answer one question: did
        pressing that control change anything? Not a summary of the page — four
        values that move when the page does, and stay put when it does not.

        **`controls` is the fourth, and it was missing.** Three structural keys
        answer "did the page become a different page"; they do not answer "did
        the page respond", and those are different questions. An application that
        reacts to a press by *changing what it offers* — revealing a validation
        message, enabling the submit button it was holding shut, swapping a
        sign-in form for a signed-in header — can do all of that with the url,
        the title and the accessibility node count identical, and the run filed
        `effect: unchanged` for an app the reader could see answering. The
        control set is the page's own account of what can be pressed, which is
        the same account the planner wrote its script from, so an action that
        changes it has visibly changed the page by the only standard this plane
        already uses.

        Read WITHOUT `value`, deliberately, and this is the one exclusion that
        matters. A field's value always changes when it is typed into, so
        including it would make every type report `changed` — including a type
        into a box wired to nothing, which is exactly the inert control this
        fingerprint exists to catch. What a field holds is the subject of
        `field_value:`, a claim of its own; what the page *offers* is this.
        """
        try:
            return {
                "url": self._page.url,
                "title": await self._page.title(),
                "node_count": len(
                    (await self._page.locator("body").aria_snapshot()).splitlines()
                ),
                "controls": _control_shape(await self._controls()),
            }
        except Exception:  # noqa: BLE001 — a page mid-navigation still has a url
            return {"url": self._page.url, "title": "", "node_count": 0, "controls": []}

    async def _page_state(self) -> dict:
        """The fingerprint under the keys an Observation carries."""
        state = await self._state()
        return {
            "page_url": state["url"],
            "page_node_count": state["node_count"],
            "page_fingerprint": f'{state["url"]}|{state["title"]}|{state["node_count"]}',
        }

    async def _controls(self) -> list[dict]:
        """Every control the page offers, as data the planner can write a script from.

        The aria snapshot above already contains all of this — as YAML indented by
        nesting depth. Handing the planner that blob means every consumer has to
        re-parse it, and a parser that disagrees with the page about indentation
        invents a control that is not there. So the page is asked directly, and
        each control arrives with the three things a script step needs: what it
        IS (role), what it is CALLED (name), and how to ADDRESS it (selector).

        `selector` is a Playwright role selector — `role=button[name="Sign in"]` —
        rather than a CSS path, because it is built from the same accessible name
        a human reads on the screen. A CSS path survives a restyle and breaks on a
        re-render; a role selector does the opposite, and the name it carries is
        the thing the trace can show the user.

        Bounded at 60: a page with more controls than that has more script than one
        run's budget can execute, and a truncated list still names the ones a
        person would point at first (DOM order — the top of the page).
        """
        try:
            return await self._page.evaluate(
                """() => {
                  const SEL = 'a[href], button, input, select, textarea, [role=button], [role=link], [role=tab]';
                  const clean = (s) => (s || '').replace(/\\s+/g, ' ').trim().slice(0, 80);
                  const forms = Array.from(document.forms);
                  const out = [];
                  for (const el of document.querySelectorAll(SEL)) {
                    const tag = el.tagName.toLowerCase();
                    const explicit = el.getAttribute('role');
                    let role = explicit;
                    if (!role) {
                      if (tag === 'a') role = 'link';
                      else if (tag === 'button') role = 'button';
                      else if (tag === 'select') role = 'combobox';
                      else if (tag === 'textarea') role = 'textbox';
                      else if (tag === 'input') {
                        const t = (el.getAttribute('type') || 'text').toLowerCase();
                        if (t === 'submit' || t === 'button' || t === 'reset' || t === 'image') role = 'button';
                        else if (t === 'checkbox') role = 'checkbox';
                        else if (t === 'radio') role = 'radio';
                        else role = 'textbox';
                      } else role = 'button';
                    }
                    // The accessible name a screen reader would announce, which is
                    // also what the trace shows and what the user recognises.
                    let name = clean(
                      el.getAttribute('aria-label') ||
                      (el.labels && el.labels[0] && el.labels[0].textContent) ||
                      el.getAttribute('placeholder') ||
                      el.textContent ||
                      el.getAttribute('value') ||
                      el.getAttribute('name') ||
                      el.getAttribute('title')
                    );
                    if (!name) continue;
                    const rect = el.getBoundingClientRect();
                    const form = el.form || null;
                    out.push({
                      role,
                      name,
                      selector: `role=${role}[name="${name.replace(/"/g, '\\\\"')}"]`,
                      tag,
                      input_type: tag === 'input' ? (el.getAttribute('type') || 'text').toLowerCase() : null,
                      html_name: el.getAttribute('name'),
                      href: tag === 'a' ? el.href : null,
                      disabled: Boolean(el.disabled) || el.getAttribute('aria-disabled') === 'true',
                      // A control the user cannot see is one the script must not
                      // press: Playwright's own click waits for visibility, so a
                      // hidden control would turn into an action timeout rather
                      // than a finding. Zero-area is how a collapsed panel reads.
                      visible: rect.width > 0 && rect.height > 0,
                      in_form: Boolean(form),
                      // Which form, and where it posts. The index groups a form's
                      // fields with its own submit button — without it a page with
                      // two forms gets a script that fills one and submits the
                      // other. The action is the absolute target, so a script can
                      // refuse to submit a form that posts off the allowlisted host
                      // instead of spending a budget slot on a request the page's
                      // own egress guard will abort.
                      form_index: form ? forms.indexOf(form) : null,
                      form_action: form ? form.action : null,
                      // A field that already holds a value is one the run should
                      // not overwrite: `required` and `value` together are what let
                      // the script skip a pre-filled field rather than clobber it.
                      required: Boolean(el.required),
                      value: tag === 'input' || tag === 'textarea' || tag === 'select'
                        ? clean(el.value) : '',
                    });
                    if (out.length >= 60) break;
                  }
                  return out;
                }"""
            )
        except Exception:  # noqa: BLE001 — a page with no controls is a page with none
            return []

    async def _field_value(self, selector: str) -> str | None:
        """What the field holds after a type, or None if it cannot be read."""
        try:
            return await self._page.input_value(selector, timeout=self._action_timeout)
        except Exception:  # noqa: BLE001
            return None

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


#: The fields of a control that a watching surface shows, out of the fourteen
#: `_controls` collects. The rest exist so a *script* can be written from the
#: control — which form it belongs to, whether it is required, where the form
#: posts — and a pane that showed them would be showing a reader the reasons the
#: wizard decided something instead of the page they are watching it decide about.
#: `disabled` and `visible` stay because a control that cannot be pressed is the
#: one thing about it a viewer needs to know before asking why nothing happened.
#:
#: `selector` stays for a different reason: it is the control's identity, and a
#: pane that wants to point at the button the run just pressed has to be able to
#: say which control that was. The action event carries the selector it acted on,
#: so matching the two is the only way to mark it — and the alternative, having
#: the viewer rebuild a selector out of role and name, is a second copy of a rule
#: that already exists once and would drift the moment it changed.
_VIEW_CONTROL_KEYS = ("role", "name", "selector", "disabled", "visible", "value",
                      "input_type")


def _control_shape(controls: list[dict]) -> list[tuple]:
    """What the page offers, as a value two readings can be compared on.

    Every key of `_VIEW_CONTROL_KEYS` except `value` — the one key that moves for
    a reason that is not a response. Kept as tuples in DOM order rather than a
    set, because the order controls appear in is part of what the page is, and a
    count alone would call two entirely different pages the same.

    A missing key becomes `None` rather than being dropped, so two controls that
    differ only by a key one of them omits do not compare equal.
    """
    return [
        tuple(c.get(k) for k in _VIEW_CONTROL_KEYS if k != "value")
        for c in controls
        if isinstance(c, dict)
    ]


def _effect(before: dict, after: dict) -> str:
    """Whether an interaction changed the page: "changed" or "unchanged".

    This is the difference between *operating* an app and *walking* it. A walk
    records that a control was pressed; this records what pressing it did, and
    "nothing" is a real answer — a button wired to nothing, a form that rejects
    its own submit, a tab that does not switch. An action that always reported
    success would make all three look like a working app, which is the failure
    mode this whole plane exists to avoid.

    Compared on url + title + node count + the page's control set, and the
    control set is what makes this answer the question it claims to. The first
    three say the page became a *different* page; a page that responds without
    navigating keeps all three and still offers something new, and calling that
    "unchanged" is how a run that visibly worked came out looking inert. Read
    without `value` — see `_state` — because a field always holds what it was
    just typed into, and counting that as a response would make an inert box and
    a working one identical.

    Text is deliberately still absent from the fingerprint: text moves when a
    counter ticks, and a page that reformats what it already shows has not done
    anything a reader would call an effect. The control set does not tick — it
    changes when the page offers something different to press.
    """
    if before == after:
        return "unchanged"
    for key in ("url", "title", "node_count", "controls"):
        if before.get(key) != after.get(key):
            return "changed"
    return "unchanged"

