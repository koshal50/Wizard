"""Investigation-scoped agent-browser sessions and the existing Runtime registry."""
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
