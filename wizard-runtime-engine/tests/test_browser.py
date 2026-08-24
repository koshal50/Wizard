"""Agentic browser — deterministic integration tests.

These run WITHOUT a real browser (playwright is imported lazily), so they cover
the whole kernel surface: tool registration, the URL egress guard, dedup policy,
extractors, trust tier, observation typing, options plumbing, the factory, the
per-investigation registry, and narration emission. A guarded smoke test exercises
a real Chromium only when playwright + a browser binary are actually present.
"""
from __future__ import annotations

import importlib.util
from datetime import datetime

import pytest

from wizard_kernel.belief import extractors
from wizard_kernel.belief.trust import source_tier_for_tool
from wizard_kernel.contracts.agent import ToolRequest
from wizard_kernel.contracts.observation import Observation
from wizard_kernel.contracts.request import InvestigationOptions
from wizard_kernel.control.tool_validator import ToolRequestValidator
from wizard_kernel.session import events as event_bus
from wizard_kernel.world.tools import ToolExecutor, _REGISTERED_TOOLS

_BROWSER_TOOLS = (
    "browser_navigate", "browser_snapshot", "browser_click",
    "browser_type", "browser_back", "browser_extract",
)


def _obs(obs_type: str, payload: dict, tool: str = "browser_navigate") -> Observation:
    return Observation(
        id="o1", investigation_id="inv1", node_id="n1",
        source_tool=tool, obs_type=obs_type, payload=payload,
        created_at=datetime(2026, 1, 1),
    )


class _FakeBrowser:
    """Stand-in BrowserRuntime — returns canned data dicts, never launches Chromium."""
    def navigate(self, url):   return {"url": url, "status": 200, "title": "Example"}
    def snapshot(self):        return {"url": "https://x.test/", "title": "X", "snapshot": "[link: Home]",
                                       "node_count": 1, "links": [{"text": "Home", "href": "https://x.test/"}]}
    def click(self, selector): return {"selector": selector, "clicked": True, "url": "https://x.test/"}
    def fill(self, selector, text): return {"selector": selector, "typed": True, "url": "https://x.test/"}
    def back(self):            return {"url": "https://x.test/", "status": 200, "title": "X"}
    def extract(self):         return {"url": "https://x.test/", "title": "X", "text": "hi",
                                       "links": [{"text": "Home", "href": "https://x.test/"}]}


# ── Tool registration & executor ────────────────────────────────────────────

def test_browser_tools_registered():
    for t in _BROWSER_TOOLS:
        assert t in _REGISTERED_TOOLS


def test_executor_browser_disabled_returns_error():
    tools = ToolExecutor(sandbox=None, repo_path=".", browser=None)
    out = tools.execute({"tool": "browser_snapshot", "params": {}})
    assert out["ok"] is False
    assert "not enabled" in out["error"]


def test_executor_browser_passthrough_envelope():
    tools = ToolExecutor(sandbox=None, repo_path=".", browser=_FakeBrowser())
    nav = tools.execute({"tool": "browser_navigate", "params": {"url": "https://example.com"}})
    assert nav["ok"] and nav["data"]["status"] == 200 and nav["error"] is None
    snap = tools.execute({"tool": "browser_snapshot", "params": {}})
    assert snap["ok"] and snap["data"]["node_count"] == 1
    typed = tools.execute({"tool": "browser_type", "params": {"selector": "#q", "text": "hi"}})
    assert typed["ok"] and typed["data"]["typed"] is True


def test_executor_browser_exception_becomes_error(monkeypatch):
    class Boom(_FakeBrowser):
        def navigate(self, url): raise RuntimeError("nav timeout")
    tools = ToolExecutor(sandbox=None, repo_path=".", browser=Boom())
    out = tools.execute({"tool": "browser_navigate", "params": {"url": "https://example.com"}})
    assert out["ok"] is False and "nav timeout" in out["error"]  # invariant 4


# ── URL egress guard (fail-closed allowlist) ────────────────────────────────

def test_url_guard_fail_closed_empty_allowlist():
    v = ToolRequestValidator(".", allowed_domains=[])
    r = v.validate(ToolRequest(tool="browser_navigate", parameters={"url": "https://example.com"}), 10)
    assert not r.valid and "fail-closed" in r.reason


def test_url_guard_allows_listed_domain_and_subdomain():
    v = ToolRequestValidator(".", allowed_domains=["example.com"])
    assert v.validate(ToolRequest(tool="browser_navigate", parameters={"url": "https://example.com/a"}), 10).valid
    assert v.validate(ToolRequest(tool="browser_navigate", parameters={"url": "https://docs.example.com"}), 10).valid


def test_url_guard_blocks_unlisted_and_lookalike_and_scheme():
    v = ToolRequestValidator(".", allowed_domains=["example.com"])
    assert not v.validate(ToolRequest(tool="browser_navigate", parameters={"url": "https://evil.com"}), 10).valid
    # lookalike must not pass the subdomain check
    assert not v.validate(ToolRequest(tool="browser_navigate", parameters={"url": "https://evil-example.com"}), 10).valid
    # non-http scheme rejected
    assert not v.validate(ToolRequest(tool="browser_navigate", parameters={"url": "file:///etc/passwd"}), 10).valid


# ── Dedup policy: browser tools excluded, file tools still deduped ───────────

def test_browser_tools_excluded_from_dedup():
    v = ToolRequestValidator(".", allowed_domains=["x.test"])
    req = ToolRequest(tool="browser_snapshot", parameters={})
    assert v.validate(req, 10).valid
    assert v.validate(req, 10).valid  # identical params, still allowed (page changed)


def test_non_browser_tools_still_deduped():
    v = ToolRequestValidator(".")
    req = ToolRequest(tool="read_file", parameters={"path": "a.txt"})
    assert v.validate(req, 10).valid
    assert not v.validate(req, 10).valid  # exact duplicate rejected


def test_browser_structural_validation():
    v = ToolRequestValidator(".", allowed_domains=["x.test"])
    # browser_type requires text
    r = v.validate(ToolRequest(tool="browser_type", parameters={"selector": "#q"}), 10)
    assert not r.valid and "text" in r.reason


# ── Extractors (claim type WEB) ─────────────────────────────────────────────

def test_extract_browser_action():
    obs = _obs("browser_action", {"ok": True, "data": {"url": "https://x.test/", "status": 200, "title": "X"}})
    results = {(r.claim_type, r.key): r for r in extractors.extract(obs)}
    assert results[("WEB", "current_url")].value == "https://x.test/"
    assert results[("WEB", "page_title")].value == "X"
    assert results[("WEB", "http_status:https://x.test/")].support_type == "support"


def test_extract_browser_action_bad_status_contradicts():
    obs = _obs("browser_action", {"ok": True, "data": {"url": "https://x.test/", "status": 500}})
    hit = next(r for r in extractors.extract(obs) if r.key.startswith("http_status:"))
    assert hit.support_type == "contradict"


def test_extract_page_content():
    obs = _obs("page_content", {"ok": True, "data": {
        "url": "https://x.test/", "title": "X", "node_count": 12,
        "links": [{"text": "a", "href": "h"}], "text": "hello"}}, tool="browser_snapshot")
    results = {(r.claim_type, r.key): r.value for r in extractors.extract(obs)}
    assert results[("WEB", "a11y_node_count")] == 12
    assert results[("WEB", "link_count")] == 1
    assert results[("WEB", "has_text_content")] is True


# ── Trust tier, obs typing, options, factory, registry, narration ───────────

def test_browser_tools_are_execution_tier():
    for t in _BROWSER_TOOLS:
        assert source_tier_for_tool(t) == "execution"


def test_observation_accepts_browser_types():
    for t in ("page_content", "browser_action"):
        assert _obs(t, {"ok": True}).obs_type == t


def test_options_browser_fields_default_off():
    opts = InvestigationOptions()
    assert opts.browser_enabled is False and opts.browser_backend == "local" and opts.allowed_domains == []
    opts2 = InvestigationOptions(browser_enabled=True, allowed_domains=["example.com"])
    assert opts2.browser_enabled and opts2.allowed_domains == ["example.com"]


def test_factory_backends():
    from wizard_kernel.world.browser import get_browser, BrowserRuntime
    assert isinstance(get_browser({}), BrowserRuntime)
    cdp = get_browser({"browser_backend": "cdp_url", "browser_cdp_url": "ws://host/x"})
    assert cdp._backend == "cdp_url" and cdp._cdp_url == "ws://host/x"


def test_registry_roundtrip():
    from wizard_kernel.world import browser as bmod
    rt = _FakeBrowser()
    bmod.register_runtime("invX", rt)
    assert bmod.get_runtime("invX") is rt
    bmod.unregister_runtime("invX")
    assert bmod.get_runtime("invX") is None


def test_narration_helper_emits_events():
    from wizard_kernel.control.loop import _emit_browser_narration
    bus = event_bus.EventBus("inv1")
    _emit_browser_narration(bus, "browser_navigate", {"url": "https://x.test/", "status": 200, "title": "X"})
    _emit_browser_narration(bus, "browser_click", {"url": "https://x.test/", "selector": "#go"})
    _emit_browser_narration(bus, "browser_extract", {"url": "https://x.test/", "title": "X",
                                                     "node_count": 3, "links": [1, 2]})
    types = [e.event_type for e in bus.get_recent_events(0)]
    assert types == ["browser.navigated", "browser.acted", "browser.extracted"]


# ── Live smoke test — only if a real browser is available ───────────────────

@pytest.mark.skipif(importlib.util.find_spec("playwright") is None, reason="playwright not installed")
def test_live_browser_smoke():
    from wizard_kernel.world.browser import BrowserRuntime
    br = BrowserRuntime(backend="local")
    try:
        br.start()
    except Exception as exc:  # noqa: BLE001 — no chromium binary in this env
        pytest.skip(f"chromium not launchable: {exc}")
    try:
        nav = br.navigate("about:blank")
        assert nav["url"] == "about:blank"
        snap = br.snapshot()
        assert "snapshot" in snap and "url" in snap
    finally:
        br.stop()
