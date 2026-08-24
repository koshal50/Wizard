"""Agentic browser subsystem — a browser action is just another Wizard tool.

Net-new and self-contained: it owns the Playwright lifecycle (``runtime.py``), a
factory that mirrors ``world/sandbox`` (``factory.py``), and a per-investigation
registry so the async ``/screencast`` route can find an investigation's live page
by id — mirroring the ``EventBus`` registry in ``session/events.py``. Nothing here
is imported unless an investigation sets ``browser_enabled=True``.
"""
from __future__ import annotations

from wizard_kernel.world.browser.factory import get_browser
from wizard_kernel.world.browser.runtime import BrowserRuntime

# Per-investigation registry (invariant 6 — never shared). The screencast
# WebSocket looks up the live BrowserRuntime here by investigation id.
_RUNTIMES: dict[str, BrowserRuntime] = {}


def register_runtime(inv_id: str, runtime: BrowserRuntime) -> None:
    _RUNTIMES[inv_id] = runtime


def get_runtime(inv_id: str) -> BrowserRuntime | None:
    return _RUNTIMES.get(inv_id)


def unregister_runtime(inv_id: str) -> None:
    _RUNTIMES.pop(inv_id, None)


__all__ = [
    "BrowserRuntime",
    "get_browser",
    "register_runtime",
    "get_runtime",
    "unregister_runtime",
]
