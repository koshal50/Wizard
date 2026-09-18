"""get_browser — the browser-plane mirror of ``world/sandbox.get_sandbox``.

Backends (see agentic-browser-architecture.md §7, §10):

- ``"local"``   — launch Chromium in this environment (default; works after
                  ``playwright install chromium``). Dev/CI friendly, one dependency.
- ``"cdp_url"`` — connect over CDP to an EXTERNAL, sandboxed Chromium (a Steel
                  session, browserless, or a Playwright-image container you run).
                  This is the isolated / egress-limited production path (§6). Steel
                  is not a separate code path — it *is* a ``cdp_url`` (YAGNI).
- ``"container"`` — reserved. Per-investigation container orchestration is a
                  deferred open decision (§10.1); when a ``browser_cdp_url`` is
                  supplied we bind to it, otherwise we fall back to ``"local"``
                  with a warning rather than pretend isolation exists.
"""
from __future__ import annotations

import logging

from wizard_kernel.world.browser.runtime import BrowserRuntime

log = logging.getLogger(__name__)


def get_browser(options: dict) -> BrowserRuntime:
    backend = options.get("browser_backend", "local")
    cdp_url = options.get("browser_cdp_url")
    # Only the local backend honours this: a browser reached over CDP belongs to
    # whoever is hosting it, and its window (if it has one) is their decision.
    headless = options.get("browser_headless", True)
    # The egress allowlist reaches the page itself, not just the navigate tool.
    # A click that follows a link, a form that posts to another origin, a page
    # that fetches a third-party script — none of those are `browser_navigate`,
    # and all of them leave the host just the same. Guarding only the tool left
    # the boundary open the moment the run could press anything.
    allowed_domains = list(options.get("allowed_domains") or [])

    if backend == "cdp_url":
        return BrowserRuntime(backend="cdp_url", cdp_url=cdp_url,
                              allowed_domains=allowed_domains)
    if backend == "container":
        if cdp_url:
            return BrowserRuntime(backend="cdp_url", cdp_url=cdp_url,
                                  allowed_domains=allowed_domains)
        log.warning(
            "browser_backend 'container' without browser_cdp_url — container "
            "orchestration is deferred (see architecture §10.1); launching a local browser"
        )
        return BrowserRuntime(backend="local", headless=headless,
                              allowed_domains=allowed_domains)
    return BrowserRuntime(backend="local", headless=headless,
                          allowed_domains=allowed_domains)

