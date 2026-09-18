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


# ── The page as a viewer sees it (not as the planner scripts it) ────────────

def test_every_browser_event_carries_the_page():
    """A pane fed from one of the three would go blank on the other two.

    `browser_navigate` returns a url and a title and knows nothing about
    controls; `browser_click` returns the fingerprint it compared and knows
    nothing about them either. Only `browser_snapshot` reads the controls at all
    — so if the page rode on that event alone, a viewer would watch the page
    appear once and then sit unchanged through every interaction, which is
    precisely the part worth watching.
    """
    from wizard_kernel.control.loop import _emit_browser_narration
    bus = event_bus.EventBus("inv1")
    page = {"url": "https://x.test/", "title": "X", "node_count": 4,
            "controls": [{"role": "button", "name": "Sign in", "selector": "role=button[name=\"Sign in\"]"}]}
    for tool, data in (("browser_navigate", {"url": "https://x.test/", "status": 200}),
                       ("browser_click", {"url": "https://x.test/", "selector": "#go"}),
                       ("browser_snapshot", {"url": "https://x.test/", "title": "X"})):
        _emit_browser_narration(bus, tool, data, page=page)
    for event in bus.get_recent_events(0):
        assert event.payload["page"] == page


def test_a_page_that_could_not_be_read_is_absent_not_null():
    """`None` and `{}` are different claims, and only one of them is honest.

    An absent key says "this event carried no page" — the pane keeps what it
    had. A `None` under the key says "the page is null", which a viewer would be
    entitled to read as "there is no page", and on a run whose browser has
    crashed that is a stronger statement than the kernel can make.
    """
    from wizard_kernel.control.loop import _emit_browser_narration
    bus = event_bus.EventBus("inv1")
    _emit_browser_narration(bus, "browser_navigate", {"url": "https://x.test/"}, page=None)
    assert "page" not in bus.get_recent_events(0)[0].payload


def test_page_view_is_shaped_for_reading_not_for_scripting():
    """Fourteen fields go to a script; a pane gets the seven it can print.

    The dropped ones are not decoration — `form_action`, `required` and
    `form_index` are how the planner decides which button submits which form.
    Showing them would put the wizard's reasons on the pane beside the page,
    which is a different thing from showing the page.
    """
    import asyncio
    from wizard_kernel.world.browser.runtime import BrowserRuntime

    rt = BrowserRuntime.__new__(BrowserRuntime)   # no Chromium: only the shaping is under test

    async def _state():
        return {"url": "https://x.test/login", "title": "Sign in", "node_count": 7}

    async def _controls():
        return [{
            "role": "button", "name": "Sign in", "selector": 'role=button[name="Sign in"]',
            "tag": "button", "input_type": None, "html_name": "go", "href": None,
            "disabled": False, "visible": True, "in_form": True, "form_index": 0,
            "form_action": "https://x.test/login", "required": False, "value": "",
        }]

    rt._state, rt._controls = _state, _controls
    view = asyncio.run(rt._a_page_view())
    assert view["url"] == "https://x.test/login" and view["node_count"] == 7
    assert set(view["controls"][0]) == {
        "role", "name", "selector", "disabled", "visible", "value", "input_type",
    }
    assert "form_action" not in view["controls"][0]


def test_page_view_returns_none_instead_of_raising():
    """A viewer's read must never be the reason a run ends.

    Reading the page the instant a click navigates is a race the read loses
    regularly, and losing it is not an error — it is the pane being told to keep
    showing what it had until the page settles.
    """
    from wizard_kernel.world.browser.runtime import BrowserRuntime
    rt = BrowserRuntime.__new__(BrowserRuntime)
    rt._loop = None            # `_call` raises "browser not started" on this
    # Not a coroutine, so the failed read leaves nothing un-awaited behind: the
    # property under test is that the raise is swallowed, not how it is raised.
    rt._a_page_view = lambda: {"url": "unreachable"}
    assert rt.page_view() is None


def test_a_browser_that_cannot_describe_its_page_does_not_stop_the_narration():
    """The loop asks for the page through `_current_page`, which cannot raise."""
    from wizard_kernel.control.loop import _current_page

    class _Raises:
        def page_view(self): raise RuntimeError("page closed")

    class _Tools:
        browser = _Raises()

    assert _current_page(_Tools()) is None
    assert _current_page(ToolExecutor(sandbox=None, repo_path=".", browser=None)) is None
    # And a runtime that does not offer the read at all is the same answer.
    assert _current_page(ToolExecutor(sandbox=None, repo_path=".", browser=_FakeBrowser())) is None


# ── Interaction: a click is not a navigate ──────────────────────────────────

def test_click_yields_claims_a_navigate_does_not():
    """The distinction the whole plane rests on.

    Before this, click / type / navigate all produced {current_url, page_title}
    and nothing else, so a run that pressed the app's buttons and a run that
    merely walked its pages were the same run as far as the Knowledge Graph was
    concerned. No goal could depend on the difference, so the browser could only
    ever be a reader.

    The distinction is carried in the claim TYPE, not just the key, because the
    goal engine counts types and cannot tell two keys of one type apart — typing
    an interaction "WEB" would let a navigate's current_url close a goal that
    asked for the page to be operated, which is the exact bug this fixes.
    """
    nav = _obs("browser_action", {"ok": True, "data": {
        "url": "https://x.test/", "status": 200, "title": "X"}})
    nav_claims = list(extractors.extract(nav))
    nav_keys = {r.key for r in nav_claims}
    assert not any(k.startswith("interacted:") for k in nav_keys)
    assert {r.claim_type for r in nav_claims} == {"WEB"}

    click = _obs("browser_action", {"ok": True, "data": {
        "url": "https://x.test/", "selector": "role=button[name=\"Sign in\"]",
        "clicked": True, "effect": "changed"}}, tool="browser_click")
    got = {(r.key): r for r in extractors.extract(click)}
    assert got['interacted:role=button[name="Sign in"]'].value is True
    assert got['effect:role=button[name="Sign in"]'].value == "changed"
    assert 'interacted:role=button[name="Sign in"]' not in nav_keys
    assert got['interacted:role=button[name="Sign in"]'].claim_type == "INTERACTION"
    assert got['effect:role=button[name="Sign in"]'].claim_type == "INTERACTION"
    # The same observation still reports where it happened — reaching the page is
    # a WEB finding whether or not anything was done on it.
    assert got["current_url"].claim_type == "WEB"


def test_inert_control_is_supporting_not_contradicting():
    """A button that changed nothing is an observation, not an accusation.

    "effect: unchanged" is true whatever the app was supposed to do. Marking it a
    contradiction would assert the app is broken, which is a stronger claim than
    the browser is entitled to make — the reader of the report decides.
    """
    obs = _obs("browser_action", {"ok": True, "data": {
        "url": "https://x.test/", "selector": "role=button[name=\"Go\"]",
        "clicked": True, "effect": "unchanged"}}, tool="browser_click")
    hit = next(r for r in extractors.extract(obs) if r.key.startswith("effect:"))
    assert hit.value == "unchanged" and hit.support_type == "support"


def test_typed_value_is_read_back_not_assumed():
    obs = _obs("browser_action", {"ok": True, "data": {
        "url": "https://x.test/", "selector": 'role=textbox[name="Email"]',
        "typed": True, "value": "a@b.test"}}, tool="browser_type")
    got = {r.key: r for r in extractors.extract(obs)}
    assert got['interacted:role=textbox[name="Email"]'].value is True
    assert got['field_value:role=textbox[name="Email"]'].value == "a@b.test"
    assert all(
        got[k].claim_type == "INTERACTION"
        for k in ('interacted:role=textbox[name="Email"]', 'field_value:role=textbox[name="Email"]')
    )


def test_a_type_reports_its_own_effect_under_its_own_key():
    """Typing is an operation too, and its effect is not the click's effect.

    A fill was reported as `typed: true` plus the value and nothing else, so a
    controlled input that reformats, a field whose validation message appears and
    a field wired to nothing all reached the Knowledge Graph identically — the
    same blindness the click's `effect` was added to fix, left in place on the
    other half of the plane.

    The key is `field_effect:<selector>`, not `effect:<selector>`. Sharing one
    key would file a CONTRADICTS edge between "filling the email field re-rendered
    the form" and "pressing submit did not navigate", which are two different
    actions being compared as two answers to one question — an accusation about
    the app assembled out of the wizard's own bookkeeping.
    """
    obs = _obs("browser_action", {"ok": True, "data": {
        "url": "https://x.test/signup", "selector": 'role=textbox[name="Email"]',
        "typed": True, "value": "a@b.test", "effect": "changed"}}, tool="browser_type")
    got = {r.key: r for r in extractors.extract(obs)}
    assert got['field_effect:role=textbox[name="Email"]'].value == "changed"
    assert got['field_effect:role=textbox[name="Email"]'].claim_type == "INTERACTION"
    # And the click's key is left alone for the click to answer.
    assert 'effect:role=textbox[name="Email"]' not in got


def test_a_click_and_a_type_on_one_selector_do_not_contradict_each_other():
    """The two effects coexist as separate claims, each with its own finding."""
    from wizard_kernel.belief.evidence import EvidenceEngine
    from wizard_kernel.belief.knowledge_graph import KnowledgeGraph
    from wizard_kernel.reality.observations import ObservationStore

    store = ObservationStore("inv_two_effects")
    kg = KnowledgeGraph("inv_two_effects")
    engine = EvidenceEngine(kg)
    selector = 'role=combobox[name="Country"]'

    cases = [
        ("browser_type", {"typed": True, "value": "India", "effect": "changed"}),
        ("browser_click", {"clicked": True, "effect": "unchanged"}),
    ]
    for i, (tool, extra) in enumerate(cases):
        obs = store.append(node_id=f"n{i}", source_tool=tool, obs_type="browser_action",
                           payload={"ok": True, "data": {
                               "url": "https://x.test/", "selector": selector, **extra}})
        tier = source_tier_for_tool(tool)
        for result in extractors.extract(obs):
            engine.admit(inv_id="inv_two_effects", claim_type=result.claim_type,
                         key=result.key, value=result.value, obs_id=obs.id,
                         support_type=result.support_type, source_tier=tier,
                         node_id=f"n{i}")

    assert kg.trust_of(kg.find("INTERACTION", f"field_effect:{selector}")[0].id) > 0.6
    assert kg.trust_of(kg.find("INTERACTION", f"effect:{selector}")[0].id) > 0.6
    assert not any(r.rel_type == "CONTRADICTS" for r in kg.relationships()), (
        "typing and clicking were filed as contradicting evidence about one thing"
    )


def test_a_navigate_cannot_close_a_goal_that_requires_interaction():
    """Reaching the page is not operating it, and the goal engine must agree.

    This is the bug the INTERACTION type exists to fix: a run asked to log in
    navigated to the login page, satisfied "Verify Web Surface" on the navigate's
    WEB claims, and finished with the form untouched — reporting success for a
    thing it never did. A goal routed to INTERACTION must stay open until
    something was actually pressed.

    Driven through the real EvidenceEngine rather than a hand-built graph, so the
    test would fail if the admission path ever dropped the claim type or the
    execution tier that the goal's `requires_execution_evidence` depends on.
    """
    from wizard_kernel.belief.evidence import EvidenceEngine
    from wizard_kernel.control.goals import Goal, GoalEngine
    from wizard_kernel.belief.knowledge_graph import KnowledgeGraph
    from wizard_kernel.reality.observations import ObservationStore

    store = ObservationStore("inv_interaction")
    kg = KnowledgeGraph("inv_interaction")
    engine = EvidenceEngine(kg)
    goals = GoalEngine("inv_interaction")
    goals.add(Goal(
        id="goal_operate", name="Operate Web Surface",
        required_claim_types=["INTERACTION"], belief_threshold=0.6,
        requires_execution_evidence=True,
    ))

    def run(tool: str, data: dict) -> None:
        obs = store.append(node_id=f"n_{tool}", source_tool=tool,
                           obs_type="browser_action", payload={"ok": True, "data": data})
        tier = source_tier_for_tool(tool)
        for result in extractors.extract(obs):
            engine.admit(inv_id="inv_interaction", claim_type=result.claim_type,
                         key=result.key, value=result.value, obs_id=obs.id,
                         support_type=result.support_type, source_tier=tier,
                         node_id=obs.node_id)

    run("browser_navigate", {"url": "https://x.test/login", "status": 200, "title": "Sign in"})
    assert goals.evaluate_checkpoint("goal_operate", kg) is False
    assert goals.get("goal_operate").progress == 0.0, (
        "a navigate closed an interaction goal — the run can report operating a "
        "page it only loaded"
    )

    run("browser_type", {"url": "https://x.test/login",
                         "selector": 'role=textbox[name="Email"]',
                         "typed": True, "value": "a@b.test"})
    assert goals.evaluate_checkpoint("goal_operate", kg) is True
    assert goals.get("goal_operate").progress == 1.0


def test_a_web_goal_still_closes_on_a_navigate_alone():
    """The split must not make "Verify Web Surface" needlessly unsatisfiable.

    Retyping interaction claims could have gone too far the other way — a
    plain read-the-page goal that now requires something to be pressed, so every
    run pointed at a URL stays open forever. WEB keeps what a navigate produces.
    """
    from wizard_kernel.belief.evidence import EvidenceEngine
    from wizard_kernel.control.goals import Goal, GoalEngine
    from wizard_kernel.belief.knowledge_graph import KnowledgeGraph
    from wizard_kernel.reality.observations import ObservationStore

    store = ObservationStore("inv_web_goal")
    kg = KnowledgeGraph("inv_web_goal")
    engine = EvidenceEngine(kg)
    obs = store.append(node_id="n_nav", source_tool="browser_navigate",
                       obs_type="browser_action",
                       payload={"ok": True, "data": {
                           "url": "https://x.test/", "status": 200, "title": "X"}})
    tier = source_tier_for_tool("browser_navigate")
    for result in extractors.extract(obs):
        engine.admit(inv_id="inv_web_goal", claim_type=result.claim_type,
                     key=result.key, value=result.value, obs_id=obs.id,
                     support_type=result.support_type, source_tier=tier,
                     node_id="n_nav")

    goals = GoalEngine("inv_web_goal")
    goals.add(Goal(id="goal_web", name="Verify Web Surface",
                   required_claim_types=["WEB"], belief_threshold=0.6))
    assert goals.evaluate_checkpoint("goal_web", kg) is True


def test_typed_value_absent_is_not_a_claim():
    """An unreadable field claims nothing — `None` must not become a value."""
    obs = _obs("browser_action", {"ok": True, "data": {
        "url": "https://x.test/", "selector": "#q", "typed": True, "value": None}},
        tool="browser_type")
    assert not any(r.key.startswith("field_value:") for r in extractors.extract(obs))


def test_page_content_reports_control_count():
    obs = _obs("page_content", {"ok": True, "data": {
        "url": "https://x.test/", "node_count": 5,
        "controls": [{"role": "button", "name": "Go"}, {"role": "textbox", "name": "Q"}]}},
        tool="browser_snapshot")
    got = {r.key: r.value for r in extractors.extract(obs)}
    assert got["control_count"] == 2


def test_effect_compares_the_page_to_itself():
    from wizard_kernel.world.browser.runtime import _effect
    same = {"url": "https://x.test/", "title": "X", "node_count": 10}
    assert _effect(same, dict(same)) == "unchanged"
    assert _effect(same, {**same, "url": "https://x.test/next"}) == "changed"
    assert _effect(same, {**same, "node_count": 4}) == "changed"
    assert _effect(same, {**same, "title": "Y"}) == "changed"
    # A key that is not part of the fingerprint cannot move the verdict.
    assert _effect(same, {**same, "unrelated": 1}) == "unchanged"


# ── The page responded, and the run has to be able to say so ─────────────────

def _controls(**kw):
    """One control, shaped as `_state()` stores it.

    Built through `_control_shape` rather than by hand, because the shape is the
    thing under test elsewhere on this page: a fixture that kept `value` would
    be testing a fingerprint production never builds.
    """
    from wizard_kernel.world.browser.runtime import _control_shape
    control = {"role": "button", "name": "Sign in", "selector": "#go",
               "disabled": False, "visible": True, "value": "", "input_type": None}
    control.update(kw)
    return _control_shape([control])


def test_a_page_that_responds_without_navigating_has_changed():
    """**The app answered and the run said "unchanged".**

    Three structural keys answer "did the page become a *different* page". They
    do not answer "did the page respond", and those are different questions: an
    application can react to a press by changing what it offers — enabling the
    submit button it was holding shut, revealing a message — with the url, the
    title and the accessibility node count all identical. Filed as `unchanged`,
    a run that visibly worked reads as inert, which is the opposite of what this
    fingerprint is for.
    """
    from wizard_kernel.world.browser.runtime import _effect
    before = {"url": "https://x.test/", "title": "X", "node_count": 10,
              "controls": _controls(disabled=True)}
    after = {**before, "controls": _controls(disabled=False)}
    assert _effect(before, after) == "changed"


def test_a_control_appearing_or_leaving_is_a_response():
    from wizard_kernel.world.browser.runtime import _effect
    before = {"url": "https://x.test/", "title": "X", "node_count": 10,
              "controls": _controls()}
    gone = {**before, "controls": []}
    assert _effect(before, gone) == "changed"
    assert _effect(gone, before) == "changed"


def test_typing_into_a_box_wired_to_nothing_is_still_unchanged():
    """The exclusion that keeps the new key honest.

    A field's value always changes when it is typed into — including into a box
    that does nothing with it. Counting `value` would make every type report
    `changed`, and an inert input would be indistinguishable from a working one.
    The value is the subject of `field_value:`, a claim of its own.
    """
    from wizard_kernel.world.browser.runtime import _effect
    before = {"url": "https://x.test/", "title": "X", "node_count": 10,
              "controls": _controls(role="textbox", name="Email", value="")}
    after = {**before, "controls": _controls(role="textbox", name="Email",
                                             value="wizard.probe@example.test")}
    assert _effect(before, after) == "unchanged"


def test_a_control_filled_in_by_the_page_counts_as_a_response():
    """A type whose result is not the text it typed is a real effect.

    The field's own value is excluded, but if filling it makes the page offer
    something else — a validation message, an enabled button — the control set
    moved and the page responded.
    """
    from wizard_kernel.world.browser.runtime import _effect
    before = {"url": "https://x.test/", "title": "X", "node_count": 10,
              "controls": _controls(role="textbox", name="Email", value="")}
    after = {**before, "controls": _controls(role="textbox", name="Email", value="")
             + _controls(role="button", name="Continue", selector="#next")}
    assert _effect(before, after) == "changed"


def test_control_shape_drops_value_and_keeps_everything_else():
    from wizard_kernel.world.browser.runtime import _control_shape
    shaped = _control_shape([{"role": "button", "name": "Go", "selector": "#go",
                              "value": "typed", "disabled": False,
                              "visible": True, "input_type": None}])
    assert len(shaped) == 1
    assert "typed" not in shaped[0], "the value must not be part of the fingerprint"
    assert "Go" in shaped[0] and "#go" in shaped[0]


def test_control_shape_is_order_sensitive():
    """Two pages offering the same controls in a different order are two pages.

    Built from raw control dicts, because this test is about the shape function
    itself rather than about a state `_state()` produced.
    """
    from wizard_kernel.world.browser.runtime import _control_shape
    a = {"role": "button", "name": "A", "selector": "#a"}
    b = {"role": "button", "name": "B", "selector": "#b"}
    assert _control_shape([a, b]) != _control_shape([b, a])


def test_control_shape_survives_a_control_that_is_not_a_dict():
    """The controls come from JavaScript the page built."""
    from wizard_kernel.world.browser.runtime import _control_shape
    assert _control_shape([None, "x", {"role": "button"}]) == [
        ("button", None, None, None, None, None)
    ]



# ── Egress guard on the page itself (covers the click, not just navigate) ────

def test_host_rule_matches_the_validator():
    """The page-level guard must admit exactly what the tool validator admits.

    Two implementations of one policy is how a boundary ends up enforced on the
    front door and open at the window: the validator guards `browser_navigate`,
    the page guard guards everything else.
    """
    from wizard_kernel.world.browser.runtime import BrowserRuntime
    br = BrowserRuntime(allowed_domains=["example.com"])
    assert br._host_allowed("example.com")
    assert br._host_allowed("docs.example.com")
    assert not br._host_allowed("evil-example.com")
    assert not br._host_allowed("evil.com")
    assert not br._host_allowed("")


def test_host_rule_fails_closed_on_empty_allowlist():
    from wizard_kernel.world.browser.runtime import BrowserRuntime
    br = BrowserRuntime()
    assert not br._host_allowed("example.com")
    assert br.blocked_requests == []


def test_factory_passes_the_allowlist_to_the_page():
    """Not only to the validator — the guard that covers clicks needs it too."""
    from wizard_kernel.world.browser import get_browser
    br = get_browser({"allowed_domains": ["example.com"]})
    assert br._allowed == ("example.com",)
    assert get_browser({})._allowed == ()


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
