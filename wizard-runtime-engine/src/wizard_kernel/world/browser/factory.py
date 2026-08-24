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

    if backend == "cdp_url":
        return BrowserRuntime(backend="cdp_url", cdp_url=cdp_url)
    if backend == "container":
        if cdp_url:
            return BrowserRuntime(backend="cdp_url", cdp_url=cdp_url)
        log.warning(
            "browser_backend 'container' without browser_cdp_url — container "
            "orchestration is deferred (see architecture §10.1); launching a local browser"
        )
        return BrowserRuntime(backend="local")
    return BrowserRuntime(backend="local")
