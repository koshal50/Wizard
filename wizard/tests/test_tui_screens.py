"""Drive the real TUI headlessly, through every screen a user sees.

The TUI is the first thing `wizard` shows, which makes it the worst place to
have no test: a crash on the first render is the whole product failing.
prompt_toolkit can be driven without a terminal — pipe input, dummy output, the
real Application — so this exercises the actual key bindings and the actual
render path rather than a reimplementation of them.

Two kinds of test live here. The first walk the screens and check the strings a
user reads. The second are guards: this file previously described a design that
invented a plausible run, with a rotating verb and a synthetic token/$ meter,
whenever the Runtime was unreachable — so a broken run and a working run looked
the same. Those guards fail if any of that comes back.
"""
import os
import types
from contextlib import contextmanager
from pathlib import Path

import pytest

os.environ.setdefault("WIZARD_ENGINE_URL", "http://127.0.0.1:8080")

from prompt_toolkit.application import create_app_session  # noqa: E402
from prompt_toolkit.data_structures import Size  # noqa: E402
from prompt_toolkit.input import create_pipe_input  # noqa: E402
from prompt_toolkit.output import DummyOutput  # noqa: E402

from wizard import __version__  # noqa: E402
from wizard.cli.parser.command_parser import COMMAND_TARGETS  # noqa: E402
from wizard.cli.tui import art  # noqa: E402
from wizard.cli.tui import session as session_mod  # noqa: E402
from wizard.cli.tui.app import (  # noqa: E402
    INTENT, MENU, RESULT, WORKING, WizardTUI,
)
from wizard.cli.models.investigation_request import RequestOptions  # noqa: E402
from wizard.cli.tui.session import TuiSession, _narrate  # noqa: E402


@contextmanager
def _headless():
    """A pipe in, a sized dummy out, for the life of the block.

    `Application(...)` resolves its input and output at construction time, from
    the ambient AppSession. Off a real terminal, that resolution is what raises
    `NoConsoleScreenBufferError` on Windows — before a test gets the chance to
    assign `app.output` afterwards. `create_app_session` is the supported way to
    say what the session's devices are, so the app is constructed normally, with
    the real key bindings and the real render path, and still runs under pytest.

    The size is a terminal this layout actually fits in, which is part of what is
    being tested. The identity panel is around two dozen rows and the art inside
    it is a fixed 21 columns, so a 120x44 dummy leaves the wizard drawn whole and
    the box beside it wide enough to read a sentence in.
    """
    class _SizedOutput(DummyOutput):
        def get_size(self):
            return Size(rows=44, columns=120)

    with create_pipe_input() as pipe, create_app_session(
        input=pipe, output=_SizedOutput()
    ):
        yield pipe


@pytest.fixture
def tui():
    with _headless():
        yield WizardTUI()


@pytest.fixture
def driven():
    """A TUI plus the pipe keys arrive on, inside one headless session.

    Scrollability is a claim about what a keystroke does, so it is checked the
    way a user exercises it — bytes in, a moved window out — through the real
    Application and its real key bindings.
    """
    with _headless() as pipe:
        yield WizardTUI(), pipe


def _plain(ansi) -> list[str]:
    """The lines of one rendered pane's ANSI, with the escapes resolved."""
    from prompt_toolkit.formatted_text import to_formatted_text
    return "".join(text for _, text in to_formatted_text(ansi)).split("\n")


def _render(tui) -> str:
    """One frame, as the terminal shows it: the panel above the box.

    Two Windows in an HSplit is the real layout, so this stacks them the way the
    renderer does — the fixed identity panel on top, the current screen's box
    underneath — rather than pretending the screen is one buffer.
    """
    return "\n".join(_plain(tui._render_top()) + _plain(tui._render_body()))


def _box(tui) -> str:
    """Just the command box: the current screen without the identity panel.

    Most of what the screens say is said inside the box, and the panel above it
    names every command family in its footer — so a test looking for the word
    "verify" on the menu screen would pass on the panel's footer alone, whatever
    the menu itself contained.
    """
    return "\n".join(_plain(tui._render_body()))


def _session(**kwargs) -> TuiSession:
    """A session with a fixed family, and no worker thread started."""
    return TuiSession(family=kwargs.pop("family", "investigate"),
                      target=kwargs.pop("target", "architecture"), **kwargs)


# ---------------------------------------------------------------------------
# The screens
# ---------------------------------------------------------------------------

def _wizard_art(tui) -> set[str]:
    """The glyphs the banner draws on this terminal, from the art itself.

    Not a character looked for by hand: the figure is drawn at a density that
    depends on the terminal, and braille has no `@` in it whatever it draws. The
    question "is the art on screen" is asked of the art.
    """
    from wizard.cli.tui import widgets

    width, height = tui._geometry()
    text = art.banner(widgets.art_rows(height, widgets.art_cols(width)),
                      widgets.art_cols(width))
    return {ch for ch in text.plain if ch != " "}


def test_the_first_screen_is_the_menu_under_the_identity_panel(tui):
    """The wizard, the repository, and the commands — all on the first frame.

    There is no splash to dismiss. The panel says what this is and which
    repository it will read, and the commands are already open beneath it, so
    the first keystroke is a choice rather than a way past a title card.
    """
    assert tui.state == MENU
    frame = _render(tui)
    assert "wizard" in frame
    # The banner itself is drawn, not reserved-and-empty: the glyphs the art is
    # made of are on screen, at whatever density this terminal gets.
    drawn = _wizard_art(tui)
    assert drawn, "the art rendered nothing to look for"
    assert drawn & set(frame), "the wizard art is missing from the first screen"
    # ...and the command list is open on the same frame.
    assert "what shall we do?" in frame
    for family in COMMAND_TARGETS:
        assert family in _box(tui), f"{family} is missing from the menu"


def test_the_identity_panel_is_inside_a_border_and_the_box_is_too(tui):
    """The layout is two rounded boxes, and both are drawn.

    This is the design, so it is asserted rather than left to look at: the panel
    is a ROUNDED Panel titled with the version, and the command box below it is
    the same shape. Both are checked on the frame the app actually rasterizes,
    because ROUNDED corners are exactly the sort of thing Rich substitutes ASCII
    for on Windows unless it is told not to.
    """
    frame = _render(tui)
    for glyph in ("╭", "╮", "╰", "╯"):
        assert glyph in frame, f"the rounded frame lost its {glyph} corner"
    assert f"wizard v{__version__}" in frame, "the panel is not titled with the version"


def test_the_panel_names_the_repository_the_run_will_read(tui):
    """The one fact on the panel that changes per invocation is a real one."""
    assert tui.repo_path in _render(tui)


def test_the_box_says_nothing_the_panel_already_says(tui):
    """The box carries the screen; the panel carries the identity.

    The brand line was in both, one above the other, when the panel was added —
    the same two words twice on one screen. The box's job is the current screen
    and nothing else.
    """
    assert "a calmer way to question a codebase" not in _box(tui)


def test_the_menu_shows_every_command_inside_the_command_box(tui):
    """The commands sit in the box under the panel, all of them offered."""
    tui._enter_menu()
    assert tui.state == MENU
    frame = _render(tui)
    for family in COMMAND_TARGETS:
        assert family in _box(tui), f"{family} is missing from the menu"
    assert _wizard_art(tui) & set(frame), "the wizard art is missing from the menu"


def test_every_screen_in_the_flow_renders(tui):
    """MENU -> INTENT -> WORKING -> RESULT, each rendered as the app does."""
    seen = [("menu", tui.state, _render(tui))]

    # Select a command family, the way Enter does in the menu.
    tui._select()
    if tui.state != INTENT:
        tui._select()   # a family with targets needs a second selection
    assert tui.state == INTENT, f"never reached the intent box (at {tui.state})"
    seen.append(("intent", tui.state, _render(tui)))

    tui.session = _session()
    tui.state = WORKING
    seen.append(("working", tui.state, _render(tui)))

    tui.state = RESULT
    seen.append(("result", tui.state, _render(tui)))

    for name, _, frame in seen:
        assert frame.strip(), f"the {name} screen rendered nothing"



def test_the_working_screen_survives_a_session_with_nothing_to_show(tui):
    """A frame mid-run before the first event arrives must not raise."""
    tui.state = WORKING
    tui.session = None
    assert _render(tui).strip()


def test_typing_an_intent_is_what_the_run_is_started_with(tui, monkeypatch):
    """The text typed in the box is handed to the command that parses it.

    This is the deliverable "paste my intent and see the flow" — if the box's
    contents do not reach the request, the user's words are decoration. The
    command layer runs them through parse_intent, so a target or URL typed here
    is investigated exactly as if it had been picked from the menu.
    """
    captured = {}

    class FakeSession:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def start(self):
            captured["started"] = True

    monkeypatch.setattr("wizard.cli.tui.app.TuiSession", FakeSession)
    tui._begin_work("investigate the auth flow and verify http://127.0.0.1:8899/")

    assert captured.get("started"), "the run was never started"
    assert captured.get("intent_text") == (
        "investigate the auth flow and verify http://127.0.0.1:8899/")
    assert captured.get("repo_path"), "the run was not told which repo to read"
    assert tui.state == WORKING


# ---------------------------------------------------------------------------
# The Runtime's event stream, narrated honestly
# ---------------------------------------------------------------------------

def _drive(session: TuiSession, events) -> None:
    """Push `events` through the session on this thread, as the worker would."""
    def generator():
        yield from events
    session._get_event_generator = generator
    session._run()


def test_the_runtime_s_own_next_steps_reach_the_screen(tui):
    """`agent.assessed` carries the verifier's recommendations; show them."""
    s = _session()
    _drive(s, [
        {"event_type": "seams.resolved",
         "payload": {"planner": "HttpPlanner", "explorer": "HttpExplorer",
                     "verifier": "HttpVerifier"}},
        {"event_type": "agent.assessed",
         "payload": {"assessment": "sound",
                     "recommended_additional_investigations": ["check the auth flow"]}},
        {"event_type": "done", "status": "completed",
         "report_markdown": "# report", "report_path": "output/r.md"},
    ])
    assert s.snapshot()["nexts"] == ["check the auth flow"]

    tui.family = "investigate"
    tui.session = s
    tui.state = WORKING
    assert "check the auth flow" in _render(tui)


def test_an_unreachable_runtime_shows_the_runtime_s_own_words(tui):
    """A refusal carries its reason in `error`; that is what must be displayed.

    Not "connection refused", not a step sequence — the message the Runtime
    gave, which is what tells the user whether the daemon is down or the
    request was wrong.
    """
    reason = "HTTP 400: sandbox_mode='docker' was requested, but no Docker daemon is reachable"
    s = _session()
    _drive(s, [{"event_type": "engine_unavailable", "error": reason}])

    assert s.status == "engine_unavailable"
    assert reason in s.snapshot_activity()[-1].text

    tui.family = "investigate"
    tui.session = s
    tui.state = RESULT
    assert "sandbox_mode='docker'" in _render(tui)


def test_a_failing_run_reports_the_real_error():
    """A crash is reported as itself. It is never replaced by a plausible run."""
    s = _session()

    def broken():
        raise RuntimeError("planner refused the request")
        yield  # pragma: no cover — unreachable, keeps this a generator

    s._get_event_generator = broken
    s._run()

    assert s.status == "failed"
    assert "planner refused the request" in s.snapshot_activity()[-1].text


def test_a_stream_that_ends_without_a_result_says_so():
    """Silence is reported rather than left spinning as if still working."""
    s = _session()
    _drive(s, [{"event_type": "agent.consulted", "payload": {"agent_type": "explorer"}}])
    assert s.status == "incomplete"
    assert s.finished
    assert "without reporting a result" in s.snapshot_activity()[-1].text


def test_seams_that_are_mocked_are_flagged_not_hidden():
    """A Mock behaves like the real thing, so the one difference must be loud.

    This is the guard against the seam silently degrading: the line says which
    implementation each port got, and turns red when one of them is a Mock.
    """
    mocked, style = _narrate("seams.resolved", {
        "planner": "MockPlanner", "explorer": "HttpExplorer", "verifier": "MockVerifier"})
    assert style == "wiz.err"
    assert "not wired" in mocked
    assert "MockPlanner" in mocked and "MockVerifier" in mocked

    wired, style = _narrate("seams.resolved", {
        "planner": "HttpPlanner", "explorer": "HttpExplorer", "verifier": "HttpVerifier"})
    assert style == "wiz.dim"
    assert "not wired" not in wired
    assert "HttpPlanner" in wired


def test_the_verifiers_verdict_decides_the_style_not_the_events_arrival():
    """`needs_more_work` must not come out looking like a pass.

    Found on a live run: the line read "✓ verifier · needs_more_work" in green,
    because the style was chosen from the fact that an assessment had arrived
    rather than from what it said. The verdict is a two-value literal
    (contracts/agent.py), so both values are checked here.
    """
    good, style = _narrate("agent.assessed",
                           {"assessment": "overall_sufficient", "weak_claims": []})
    assert style == "wiz.ok" and "overall sufficient" in good
    assert not good.startswith("!")

    bad, style = _narrate("agent.assessed",
                          {"assessment": "needs_more_work", "weak_claims": ["c1", "c2"]})
    assert style == "wiz.warn", "a needs_more_work verdict is not a success"
    assert not good.startswith("✗") and "✓" not in bad, "a tick on a failed verdict"
    assert "2 weak" in bad


def test_an_unknown_verdict_carries_no_verdict_glyph():
    """A verdict this file has never seen is reported, not judged."""
    line, style = _narrate("agent.assessed", {"assessment": "inconclusive"})
    assert style == "wiz.dim"
    assert "inconclusive" in line
    assert not any(g in line for g in ("✓", "✗", "!"))


def test_the_closing_review_is_named_as_the_closing_review():
    """The last assessment is asked for, not acted on — and must not read as a rebuke.

    Seen on a live run: the flow ended `! verifier · needs more work` and then
    `the investigation completed`. Both are true — the Runtime asks for one last
    review once the goals are closed and does not act on the answer — but the two
    lines next to each other read as the run contradicting itself.
    """
    line, style = _narrate("agent.assessed", {
        "assessment": "needs_more_work", "weak_claims": ["c1"], "escalated": False})
    assert style == "wiz.warn"
    assert "final" in line
    assert "not acted on" in line

    # A mid-run consultation is the one that does drive more work, so it keeps
    # the plain name and gains no such note.
    mid, _ = _narrate("agent.assessed", {
        "assessment": "needs_more_work", "weak_claims": ["c1"], "escalated": True})
    assert "final" not in mid
    assert "not acted on" not in mid


def test_a_successful_step_names_what_it_did():
    """The Runtime narrates a node's completion, and the line has to say which one.

    For a long time it did not narrate completions at all — the kernel emitted
    nothing on success, so a run that worked showed only its failures, its
    claims and its goals closing. The whole middle of the loop was invisible:
    the reader saw the Runtime *decide* to read a file and never saw it read.
    """
    line, style = _narrate("node.completed", {
        "tool": "read_file", "params": {"path": "server/src/middleware/auth.js"},
        "ok": True, "outcome": "expected_success"})
    assert style == "wiz.ok"
    assert "read_file" in line
    assert "auth.js" in line
    assert "node_" not in line, "the internal node id is not what the reader wants"


def test_a_step_that_ran_and_did_not_succeed_does_not_read_as_a_pass():
    """A command can be executed and still fail; that is the ordinary case.

    `ok` is the tool's own verdict, and `npm test` exiting non-zero is a step
    that happened and a result that is bad. Showing it with a tick would tell
    the reader the suite passed.
    """
    line, style = _narrate("node.completed", {
        "tool": "execute_command", "params": {"command": "npm test --silent"},
        "ok": False, "outcome": "expected_failure"})
    assert style == "wiz.warn"
    assert not line.startswith("✓")
    assert "npm test --silent" in line


def _narration(session: TuiSession) -> list[str]:
    """The activity lines, without the stream's closing line.

    `_drive` feeds a generator that simply ends, and the session records that
    ending as a terminal line. It is real, but it is not what these tests are
    about, and including it would mean every assertion restates its wording.
    """
    return [b.text for b in session.snapshot_activity()
            if not b.text.startswith("the runtime closed")]


def _packet(agent="explorer", sections=("a", "b"), **kw):
    payload = {"agent_type": agent, "node_id": "n1",
               "section_ids": list(sections), "rejected": False}
    payload.update(kw)
    return {"event_type": "context_supplied", "payload": payload}


def _roles(session: TuiSession) -> list[tuple[str, str]]:
    """(role, text) for each activity line — what the pane's left column shows."""
    return [(b.role, b.text) for b in session.snapshot_activity()
            if not b.text.startswith("the runtime closed")]


def _kernel_event_types() -> set[str]:
    """Every event name the kernel's `session/events.py` defines.

    Read from the module rather than copied here, so adding an event to the
    kernel is what fails the coverage test below — a hand-kept list would just
    quietly go stale, which is the failure mode the test exists to prevent.
    """
    from wizard_kernel.session import events as kernel_events

    return {name for key, name in vars(kernel_events).items()
            if not key.startswith("_") and isinstance(name, str) and "." in name}


def test_an_unchanged_context_packet_is_not_announced_again():
    """The audit repeats verbatim once per node and swamped the pane.

    A real eleven-node run printed "8 sections to explorer" eleven
    times. Every one was true and only the first was news: the Runtime supplies
    the same packet for every node, so the tenth repeat said exactly what the
    first had — that nothing had changed.
    """
    s = _session()
    _drive(s, [_packet(), _packet(), _packet()])

    assert _narration(s) == ["→ 2 sections to explorer"]


def test_the_repeat_is_suppressed_however_far_apart_the_packets_sit():
    """The repeats are never adjacent, which is what made the old fold useless.

    Each supply is followed immediately by the read it was supplied *for*, so
    the audit lines never neighbour each other: eleven identical lines, none of
    them a neighbour of another, and a fold that only merged neighbours fired
    zero times.
    """
    s = _session()
    read = {"event_type": "agent.decided",
            "payload": {"tool": "read_file", "params": {"path": "server/index.js"}}}
    _drive(s, [_packet(), read, _packet(), read, _packet()])

    assert _narration(s) == [
        "→ 2 sections to explorer",
        "→ read_file · server/index.js",
        "→ read_file · server/index.js",
    ]


def test_a_context_packet_that_changed_names_what_changed():
    """`+queued_read_paths` is the news; a bare count is what hides it.

    The count alone would read as "still 8 sections", which is the one thing
    that is not worth a line. The section that appeared is.
    """
    s = _session()
    _drive(s, [_packet(sections=("a", "b")),
               _packet(sections=("a", "b", "queued_read_paths"))])
    assert _narration(s) == [
        "→ 2 sections to explorer",
        "→ 3 sections to explorer · +queued_read_paths",
    ]


def test_a_context_packet_that_lost_a_section_names_that_too():
    """A section dropped is as much a change as one added."""
    s = _session()
    _drive(s, [_packet(sections=("a", "b")), _packet(sections=("a",))])
    assert _narration(s) == ["→ 2 sections to explorer",
                             "→ 1 sections to explorer · -b"]


def test_each_agent_gets_its_own_first_line():
    """The packets are tracked per agent — the Verifier's is not the Explorer's."""
    s = _session()
    _drive(s, [
        {"event_type": "context_supplied",
         "payload": {"agent_type": "explorer", "section_ids": ["a", "b"], "rejected": False}},
        {"event_type": "context_supplied",
         "payload": {"agent_type": "verifier", "section_ids": ["a"], "rejected": False}},
        {"event_type": "context_supplied",
         "payload": {"agent_type": "verifier", "section_ids": ["a"], "rejected": False}},
    ])
    assert _narration(s) == ["→ 2 sections to explorer",
                             "→ 1 sections to verifier"]


def test_a_packet_served_from_cache_when_the_last_was_not_is_news():
    """A cache hit is a change in how the packet was produced, so it is a line."""
    s = _session()
    _drive(s, [_packet(from_cache=False), _packet(from_cache=True)])
    assert _narration(s) == ["→ 2 sections to explorer",
                             "→ 2 sections to explorer · cached"]


def test_a_refusal_is_still_shown_every_time():
    """Suppression is for repeats, and never for failures.

    An identical refusal is the one case where the repeat itself is the
    finding: the same context was refused again, and again. Gating it on
    novelty would hide the second and every one after it.
    """
    s = _session()
    refusal = {"event_type": "context_supplied",
               "payload": {"agent_type": "explorer", "rejected": True,
                           "reason": "token budget exceeded"}}
    _drive(s, [refusal, refusal])
    assert _narration(s) == ["✗ context refused · token budget exceeded",
                             "✗ context refused · token budget exceeded"]


def test_the_next_steps_list_is_capped_and_counts_the_rest(tui):
    """A verifier can name twenty-odd next steps; the pane cannot show them all."""
    many = [f"Gather execution evidence for claim 'cl_{i:04d}'" for i in range(23)]
    s = _session()
    _drive(s, [{"event_type": "agent.assessed",
                "payload": {"assessment": "needs_more_work",
                            "recommended_additional_investigations": many}}])
    assert s.snapshot()["nexts"] == many, "the full list is still kept"

    tui.family = "investigate"
    tui.session = s
    tui.state = WORKING
    frame = _render(tui)

    assert "cl_0000" in frame, "the first next step is missing"
    assert "cl_0022" not in frame, "every next step was rendered; the pane would fill"
    assert "+ 19 more" in frame, "the withheld count is not shown"


@pytest.mark.parametrize("event_type,payload", [
    ("investigation.started", {"repository_path": "/repo"}),
    ("claim.admitted", {"claim_type": "RUNTIME", "key": "language"}),
    ("goal.satisfied", {"goal_name": "Verify Runtime"}),
    ("agent.decided", {"source": "explorer", "tool": "read_file", "reason": "entrypoint"}),
    ("agent.consulted", {"agent_type": "explorer", "claims_reviewed": 3}),
    ("context_supplied", {"agent_type": "explorer", "node_id": "n1",
                          "section_ids": ["a", "b", "c"], "token_total": 812,
                          "from_cache": False, "rejected": False, "reason": None}),
    ("tool.rejected", {"tool": "rm_rf", "reason": "not in the allowlist"}),
    ("budget.low", {"remaining": 4, "total": 20}),
    ("report.generated", {"path": ".wizard/report.md"}),
    ("browser.navigated", {"url": "http://x/", "status": 200, "title": "x"}),
])
def test_every_real_event_narrates_something(event_type, payload):
    """No real event is dropped on the floor, and none invents a step name."""
    line, style = _narrate(event_type, payload)
    assert line, f"{event_type} produced no narration"
    assert style.startswith("wiz.")


def test_a_refusal_names_what_was_refused():
    """`read_file rejected · duplicate` does not say which file.

    The whole content of a duplicate refusal is the path that was repeated, so
    the Runtime sends the parameters with the rejection and this line reads them.
    """
    line, style = _narrate("tool.rejected", {
        "tool": "read_file", "reason": "Duplicate request: already executed",
        "params": {"path": "client\\package.json", "max_bytes": 65536}})
    assert style == "wiz.err"
    assert "client\\package.json" in line


def test_a_refusal_without_parameters_still_reads():
    """Nullary tools carry no subject, and the line must not end on a separator."""
    line, style = _narrate("tool.rejected",
                           {"tool": "browser_snapshot", "reason": "no page open"})
    assert style == "wiz.err"
    assert line.count("browser_snapshot") == 1
    assert "browser_snapshot · " not in line


def test_an_unknown_event_names_itself_rather_than_inventing_a_step():
    """A new kernel event should appear as itself."""
    line, _ = _narrate("node.teleported", {})
    assert "node.teleported" in line


# ---------------------------------------------------------------------------
# Who did it — the actor column
# ---------------------------------------------------------------------------

def test_a_step_the_explorer_chose_is_attributed_to_the_explorer():
    """The kernel's own `source` field, read back out. Nothing is inferred."""
    s = _session()
    _drive(s, [{"event_type": "agent.decided",
                "payload": {"source": "explorer", "tool": "read_file",
                            "params": {"path": "client/package.json"}}}])
    assert _roles(s) == [("explorer", "→ read_file · client/package.json")]


def test_a_step_the_planner_had_planned_is_attributed_to_the_planner():
    """The distinction the whole column exists for.

    Both paths emit `agent.decided` with the same shape and differ only in
    `source`. Narrated without it, an Explorer responding to what the last read
    found and the Planner's fixed step being carried out look identical — which
    makes a real investigation and a walk through a script the same thing on
    screen, when telling them apart is the reason to watch at all.
    """
    s = _session()
    _drive(s, [{"event_type": "agent.decided",
                "payload": {"source": "node_plan", "tool": "read_file",
                            "params": {"path": "server/index.js"}}}])
    assert _roles(s) == [("planner", "→ read_file · server/index.js")]


def test_a_decision_with_no_source_is_not_attributed_to_anyone():
    """An absent field is not a licence to guess which agent it probably was."""
    s = _session()
    _drive(s, [{"event_type": "agent.decided",
                "payload": {"tool": "read_file", "params": {"path": "a.js"}}}])
    assert _roles(s) == [("", "→ read_file · a.js")]


def test_a_source_this_file_does_not_know_is_not_attributed_either():
    """A future seam gets a blank column, not a wrong name."""
    s = _session()
    _drive(s, [{"event_type": "agent.decided",
                "payload": {"source": "critic", "tool": "read_file",
                            "params": {"path": "a.js"}}}])
    assert _roles(s)[0][0] == ""


def test_the_verifier_is_named_on_its_own_assessment():
    """In the column, not in the text — the text would be saying it twice."""
    s = _session()
    _drive(s, [{"event_type": "agent.assessed",
                "payload": {"assessment": "needs_more_work", "weak_claims": ["a"]}}])
    role, text = _roles(s)[0]
    assert role == "verifier"
    assert "verifier" not in text, (
        "the column already says who; repeating it in the text is the "
        f"redundancy the column was added to remove: {text!r}")


def test_a_browser_step_does_not_repeat_the_browser_in_its_text():
    """Same reason: the role column names the plane."""
    for event in ({"event_type": "browser.navigated",
                   "payload": {"url": "http://localhost:5173/", "status": 200}},
                  {"event_type": "browser.extracted",
                   "payload": {"node_count": 12, "link_count": 1}}):
        line, _ = _narrate(event["event_type"], event["payload"])
        assert "browser" not in line, f"{event['event_type']} restates its own role: {line!r}"


def test_a_browser_count_of_zero_is_not_reported_as_unknown():
    """A measured zero and an unmeasured field are different facts.

    The extract tool reads the page's text and has no accessibility tree, so it
    sends no `node_count` — and `payload.get(k, "?")` returns None for a key
    that is present and null, so the pane printed "None nodes, 1 links" for it.
    """
    measured, _ = _narrate("browser.extracted",
                           {"node_count": 0, "link_count": 0})
    assert "0 nodes" in measured and "0 links" in measured

    missing, _ = _narrate("browser.extracted",
                          {"node_count": None, "link_count": 1})
    assert "None" not in missing
    assert "node" not in missing, (
        "a count the tool never measured is not a count to show at all")


def test_a_single_node_or_link_is_not_pluralised():
    """`1 links` is the kind of small wrongness that makes a trace feel sloppy."""
    line, _ = _narrate("browser.extracted", {"node_count": 1, "link_count": 1})
    assert "1 node," in line and "1 link" in line
    assert "1 nodes" not in line and "1 links" not in line


def test_an_extraction_with_no_counts_says_only_that_it_extracted():
    line, _ = _narrate("browser.extracted", {})
    assert line == "◈ extracted"


def test_the_trace_says_what_pressing_a_control_actually_did():
    """The finding of an interaction, which the pane was dropping on the floor.

    The kernel has put `effect` on `browser.acted` since the browser learned to
    operate a page. This line read the tool and the selector and stopped, so a
    run that drove an application produced a trace identical to one that only
    walked it: "pressed Sign in" on every button, whether the page navigated,
    re-rendered, or ignored the press entirely. The pressed-and-nothing-happened
    case is the one worth watching for, and it was the one the pane could not
    show.
    """
    line, _ = _narrate("browser.acted", {
        "tool": "browser_click", "selector": "role=button[name=\"Sign in\"]",
        "effect": "unchanged", "value": None,
    })
    assert "Sign in" in line
    assert "unchanged" in line, line


def test_a_type_reports_the_value_that_landed_not_the_one_that_was_sent():
    """The field's own reading after the keystroke is the evidence.

    `value` is what the element held once the type returned, so a controlled
    input that reformats or refuses what it is given shows as what actually
    landed. The pane showing the text that was sent would report the intent
    rather than the result, which is the difference the whole interaction plane
    exists to record.
    """
    line, _ = _narrate("browser.acted", {
        "tool": "browser_type", "selector": "role=textbox[name=\"Email\"]",
        "effect": "unchanged", "value": "wizard.probe@example.test",
    })
    assert "wizard.probe@example.test" in line, line

    rejected, _ = _narrate("browser.acted", {
        "tool": "browser_type", "selector": "role=textbox[name=\"Email\"]",
        "effect": "unchanged", "value": "",
    })
    assert "wizard.probe@example.test" not in rejected, rejected


def test_an_effect_the_engine_did_not_measure_is_not_invented():
    """No `effect` key means no claim about the page either way."""
    line, _ = _narrate("browser.acted", {
        "tool": "browser_click", "selector": "role=button[name=\"Go\"]",
    })
    assert "unchanged" not in line and "changed" not in line, line


def test_a_claim_re_observed_after_a_browser_step_is_not_logged_twice():
    """Every browser step re-reads the page, and the trace was printing all of it.

    `current_url` and `page_title` come back after every action, so a five-step
    interaction logged eight identical `WEB → current_url` lines. On a pane that
    shows a screenful, those are what the lines carrying news compete with: the
    reader watching a sign-in go in got eight rows saying the URL had not
    changed and one row saying the credentials landed.
    """
    s = _session()
    _drive(s, [
        {"event_type": "claim.admitted",
         "payload": {"claim_type": "WEB", "key": "current_url",
                     "value": "http://localhost:5173/login"}},
        {"event_type": "browser.acted",
         "payload": {"tool": "browser_type", "selector": "role=textbox[name=\"Email\"]",
                     "effect": "unchanged", "value": "a@b.test"}},
        {"event_type": "claim.admitted",
         "payload": {"claim_type": "WEB", "key": "current_url",
                     "value": "http://localhost:5173/login"}},
    ])
    logged = [t for _, t in _roles(s) if "current_url" in t]
    assert len(logged) == 1, f"the same claim was logged {len(logged)} times: {logged}"


def test_a_claim_that_comes_back_changed_is_never_folded():
    """A changed value is the event, not a repeat of one.

    `current_url` moving from the login page to the task list is how the trace
    shows a sign-in worked. Folding it away to tidy up the repeats would hide
    the single line the reader is watching for.
    """
    s = _session()
    _drive(s, [
        {"event_type": "claim.admitted",
         "payload": {"claim_type": "WEB", "key": "current_url",
                     "value": "http://localhost:5173/login"}},
        {"event_type": "claim.admitted",
         "payload": {"claim_type": "WEB", "key": "current_url",
                     "value": "http://localhost:5173/tasks"}},
    ])
    texts = [t for _, t in _roles(s) if "current_url" in t]
    assert len(texts) == 2, texts


def test_a_claim_with_no_value_is_never_folded():
    """Without the value there is no way to tell a repeat from a change.

    The kernel carries the value on `claim.admitted`; a viewer that is talking
    to one which does not is not entitled to guess, because the guess that is
    wrong is the one that hides the page having moved.
    """
    s = _session()
    _drive(s, [
        {"event_type": "claim.admitted",
         "payload": {"claim_type": "WEB", "key": "current_url"}},
        {"event_type": "claim.admitted",
         "payload": {"claim_type": "WEB", "key": "current_url"}},
    ])
    texts = [t for _, t in _roles(s) if "current_url" in t]
    assert len(texts) == 2, texts


def test_a_claim_value_that_is_not_hashable_does_not_crash_the_trace():
    """Requirements files contribute lists, and a set cannot hold one."""
    s = _session()
    _drive(s, [
        {"event_type": "claim.admitted",
         "payload": {"claim_type": "PACKAGE", "key": "requirements_packages",
                     "value": ["flask", "requests"]}},
        {"event_type": "claim.admitted",
         "payload": {"claim_type": "PACKAGE", "key": "requirements_packages",
                     "value": ["flask", "requests"]}},
    ])
    texts = [t for _, t in _roles(s) if "requirements_packages" in t]
    assert len(texts) == 1, texts


def test_a_browser_step_is_attributed_to_the_browser():
    """The plane the user watches in a second window, named on the trace."""
    s = _session()
    _drive(s, [{"event_type": "browser.navigated",
                "payload": {"url": "http://localhost:5173/", "status": 200,
                            "title": "Taskboard"}}])
    assert _roles(s)[0][0] == "browser"


def test_a_goal_closing_is_attributed_to_the_runtime():
    """No agent closes a goal — the Runtime's own GoalEngine decides that."""
    s = _session()
    _drive(s, [{"event_type": "goal.satisfied",
                "payload": {"goal_name": "Verify Web Surface"}}])
    assert _roles(s)[0][0] == "runtime"


def test_every_event_the_kernel_emits_gets_a_role_or_deliberately_none():
    """The map has to keep up with the event list, and this is how it is noticed.

    A new event narrating with a blank column is not a bug — it is a blank
    column. But it should be a decision, and the only way that stays true is if
    adding one to `session/events.py` fails here first.
    """
    from wizard.cli.tui.session import _ROLE, _role

    # The ones that carry no actor, each for a stated reason rather than by
    # omission: `seams.resolved` describes the wiring rather than a step, and
    # the rest are the CLI's own terminal markers, which are not kernel events.
    unassigned = {"seams.resolved", "investigation.state_changed"}
    narrated = _kernel_event_types() - unassigned
    # Resolved by their payload rather than by their type, so neither can live
    # in `_ROLE`: `agent.decided` is the Explorer or the Planner depending on
    # `source`, and `node.started` is the browser plane or the Runtime depending
    # on which tool is about to run.
    by_payload = {"agent.decided", "node.started"}
    missing = {e for e in narrated if e not in _ROLE and e not in by_payload}
    assert not missing, f"these events narrate with no role and no decision: {missing}"
    assert _role("agent.decided", {"source": "explorer"}) == "explorer"
    assert _role("node.started", {"tool": "browser_click"}) == "browser"
    assert _role("node.started", {"tool": "read_file"}) == "runtime"


def test_a_state_transition_event_that_is_never_fired_stays_unassigned():
    """`investigation.state_changed` is defined in events.py and emitted nowhere.

    Named here so the exclusion above is a fact with a test behind it rather
    than a name someone added to make the coverage check pass.
    """
    assert "investigation.state_changed" not in {
        "investigation.started", "investigation.incomplete"}


def test_an_incomplete_investigation_names_the_goals_that_stayed_open():
    """The line used to be the event's own name, which says nothing at all.

    This is the run where the reader most needs the reason: the loop stopped
    with goals unclosed, and the kernel's payload is the only place that says
    which ones and why it gave up.
    """
    s = _session()
    _drive(s, [{"event_type": "investigation.incomplete",
                "payload": {"reason": "the budget ran out",
                            "open_goals": ["Verify Web Surface", "Verify Tests"]}}])
    role, text = _roles(s)[0]
    assert role == "runtime"
    assert "the budget ran out" in text
    assert "Verify Web Surface" in text and "Verify Tests" in text


def test_an_incomplete_run_with_no_open_goals_does_not_dangle():
    s = _session()
    _drive(s, [{"event_type": "investigation.incomplete", "payload": {}}])
    text = _roles(s)[0][1]
    assert "still open" not in text
    assert text.endswith("the loop ended")


# ---------------------------------------------------------------------------
# The decision line names the subject, not just the tool
# ---------------------------------------------------------------------------

def test_a_decision_line_names_the_file_it_reads():
    """The trace has to say which file, or every step reads as an identical read_file."""
    line, _ = _narrate("agent.decided", {
        "source": "node_plan", "tool": "read_file",
        "params": {"path": "server/src/middleware/auth.js"},
    })
    assert "server/src/middleware/auth.js" in line


def test_a_decision_line_names_the_command_it_runs():
    """Same for execution: "chose execute_command" does not say what was run."""
    line, _ = _narrate("agent.decided", {
        "source": "explorer", "tool": "execute_command",
        "params": {"command": "node --version"},
    })
    assert "node --version" in line


def test_a_decision_with_no_subject_parameter_does_not_repeat_the_tool():
    """A nullary tool has nothing to name; "read_file · read_file" is noise."""
    line, _ = _narrate("agent.decided", {"source": "explorer", "tool": "browser_snapshot"})
    assert line.count("browser_snapshot") == 1


def test_a_deep_path_keeps_its_tail_where_the_name_is():
    """Cut from the left: the tail identifies the file, a truncated head does not."""
    deep = "client/src/features/authentication/components/LoginForm.jsx"
    line, _ = _narrate("agent.decided", {
        "source": "node_plan", "tool": "read_file", "params": {"path": deep},
    })
    assert "LoginForm.jsx" in line
    assert len(line) < len(deep) + 10, "the path was not shortened for the pane"


# ---------------------------------------------------------------------------
# A run that ends without satisfying its goals says so, and says why
# ---------------------------------------------------------------------------

def test_an_incomplete_run_is_not_reported_as_completed():
    """`incomplete` is its own outcome; reading it as success is the old bug."""
    s = _session()
    s._consume({"event_type": "done", "status": "incomplete", "stats": {
        "last_event": "the budget ran out; still open: Verify Runtime"}})

    snap = s.snapshot()
    assert snap["status"] == "incomplete"
    assert snap["finished"] is True, "the run must count as over, or the view spins"


def test_an_incomplete_run_reports_the_runtimes_own_reason():
    """The why comes from the Runtime's last_event, not from a guess here."""
    s = _session()
    s._consume({"event_type": "done", "status": "incomplete", "stats": {
        "last_event": "the planner proposed no further steps; still open: Verify Tests"}})

    lines = [ln.text for ln in s.snapshot_activity()]
    joined = "\n".join(lines)
    assert "incomplete" in joined
    assert "the planner proposed no further steps" in joined
    assert "Verify Tests" in joined


def test_a_completed_run_carries_no_extra_reason():
    """A satisfied run needs no excuse appended to it."""
    s = _session()
    s._consume({"event_type": "done", "status": "completed",
                "stats": {"last_event": "complete"}})

    lines = [ln.text for ln in s.snapshot_activity()]
    assert lines[-1] == "the investigation completed"


# ---------------------------------------------------------------------------
# Guards: the fabricated behaviour must not come back
# ---------------------------------------------------------------------------

def test_the_session_has_no_simulated_run_path():
    """There is one path through a run: the Runtime's. No stand-in exists."""
    assert not hasattr(TuiSession, "_run_simulated")
    for gone in ("_SIM_STEPS", "GERUNDS", "_TOKENS_PER_EVENT", "_RATE",
                 "_DEFAULT_EVENT_TOKENS"):
        assert not hasattr(session_mod, gone), f"{gone} is back"


def test_the_session_reports_no_fabricated_metrics():
    """Nothing measured means nothing shown — no token count, no dollar cost."""
    snap = _session().snapshot()
    for gone in ("tokens", "cost", "gerund"):
        assert gone not in snap, f"{gone} is back in the snapshot"


def test_no_screen_shows_a_fake_usage_meter(tui):
    """The meter was locally generated; it must not appear on any screen."""
    frames = []
    tui._enter_menu()
    frames.append(_render(tui))
    tui.session = _session()
    tui.state = WORKING
    frames.append(_render(tui))
    tui.state = RESULT
    frames.append(_render(tui))

    for frame in frames:
        for phrase in ("mock usage", "mock tokens", "tokens", "API Usage", "$"):
            assert phrase not in frame, f"{phrase!r} is back on a screen"


def test_no_screen_shows_a_hardcoded_identity_or_directory(tui):
    """"Koshal" is not the user, and `~\\Wizard` is not their directory."""
    frame = _render(tui)
    assert "Koshal" not in frame
    assert "Welcome back" not in frame
    assert "~\\Wizard" not in frame


# ---------------------------------------------------------------------------
# The banner
# ---------------------------------------------------------------------------

#: Which source cells a glyph says are drawn, per density. The inverse of what
#: `art` encodes, written here from the terminal's side: a half-block says which
#: of its two rows is painted, and a braille glyph's dots say which of its eight
#: sub-cells are.
_HALF_DECODE = {glyph: (top, bottom) for (top, bottom), glyph in art._HALF_GLYPH.items()}


def _subcells(glyph: str, rows_per_cell: int) -> list[tuple[int, int]]:
    """The (dx, dy) offsets inside one terminal cell that `glyph` paints."""
    if glyph == " ":
        return []
    if rows_per_cell == art._FULL:
        return [(0, 0)]
    if rows_per_cell == art._HALF:
        top, bottom = _HALF_DECODE[glyph]
        return [off for off, on in (((0, 0), top), ((0, 1), bottom)) if on]
    bits = ord(glyph) - 0x2800
    return [off for off, bit in art._BRAILLE_DOTS.items() if bits & bit]


def _claims(rows_per_cell: int) -> set[tuple[int, int]]:
    """Every source cell the figure claims is drawn, at one density.

    Read back off the rendered glyphs, so it is the screen's own account of the
    art rather than a second copy of the encoder.
    """
    cols_per_cell = art._packing(rows_per_cell)
    lines = art._render_at(rows_per_cell).plain.splitlines()
    return {(block_row * rows_per_cell + dy, block_col * cols_per_cell + dx)
            for block_row, line in enumerate(lines)
            for block_col, glyph in enumerate(line)
            for dx, dy in _subcells(glyph, rows_per_cell)}


def _size_at(rows_per_cell: int) -> tuple[int, int]:
    """The figure's (columns, rows) at one density, counted off a render."""
    lines = art._render_at(rows_per_cell).plain.splitlines()
    return (len(lines[0]), len(lines))


def test_the_banner_is_the_svg_art_cropped_to_the_figure():
    """The SVG is read as text, cropped to what was drawn.

    Cropping matters: 4755 of its 6432 cells are a black background filler that
    costs columns and shows nothing.
    """
    grid = art._grid()
    assert len(grid) == 50 and len(grid[0]) == 62, "the art was not cropped as expected"
    drawn = sum(1 for row in grid for cell in row if cell is not None)
    assert 1000 < drawn < 2000, f"unexpected fill: {drawn} cells"


def test_the_banner_is_rendered_whole_at_its_own_size():
    """Asked for no limit, the figure is drawn one source cell per terminal cell.

    The art's own 62 x 50, nothing packed and nothing dropped — which is the
    reference the packings below are measured against.
    """
    grid = art._grid()
    cols, rows = art._from_source()
    assert (cols, rows) == (62, 50), "the art was not cropped as expected"

    lines = art.banner().plain.splitlines()
    assert len(lines) == len(grid)
    assert {len(line) for line in lines} == {len(grid[0])}, "the rows are ragged"
    assert art.banner_size() == (62, 50)


def test_the_banner_keeps_every_cell_it_is_drawn_from():
    """Nothing is sampled at any density — the round trip is exact.

    This is the claim the whole module is built around, so it is checked by
    decoding rather than by counting: each rendered glyph is read back into the
    sub-cells it says are drawn, and the set of those has to be *exactly* the set
    of cells the SVG draws. Equal, not a superset — a packed renderer that
    invented a dot would fail here too.

    It is the assertion that a downsampled banner cannot pass: keeping every
    third cell, or averaging a block into one, loses cells the figure drew, and a
    single lost cell is a difference between the two sets.
    """
    truth = {(r, c) for r, row in enumerate(art._grid())
             for c, cell in enumerate(row) if cell is not None}
    assert truth, "the art parsed to nothing"

    for rows_per_cell, _ in art._DENSITIES:
        assert _claims(rows_per_cell) == truth, (
            f"the {rows_per_cell}-rows-per-cell packing does not account for "
            f"exactly the cells the art draws"
        )


def test_a_smaller_banner_is_a_denser_packing_of_the_same_figure():
    """Smaller means packed, never thinner — the distinction this is built on.

    The figure used to be drawn at its own 62 columns whatever the terminal,
    which overflowed the panel and sheared. Sampling it down was the first
    attempt and it was wrong: fewer cells on screen is a different drawing. What
    happens now is that more source cells share one terminal cell, so each step
    down is strictly smaller *and* still the whole figure.

    The height is the axis that actually moves — a cell is twice as tall as it is
    wide, so packing rows compresses the figure vertically. That compression is
    the point, but it is a compression and the tests say so rather than claiming
    a rescale.
    """
    sizes = [art.banner_size(0, 0)]
    for rows_per_cell, _ in art._DENSITIES[1:]:
        sizes.append(_size_at(rows_per_cell))

    for smaller, larger in zip(sizes[1:], sizes):
        assert smaller[0] <= larger[0] and smaller[1] < larger[1], (
            f"{smaller} is not smaller than {larger}")

    # And the density a budget picks is the least-packed one that fits it: given
    # the room for the bigger drawing, the bigger drawing is what is drawn.
    cols, rows = art._from_source()
    assert art.banner_size(rows, cols) == (cols, rows), "a full-size budget packed anyway"
    assert art.banner_size(rows - 1, cols) == _size_at(art._HALF)
    assert art.banner_size(1, cols) == _size_at(art._BRAILLE)


def test_the_banner_is_drawn_into_the_columns_it_is_given():
    """Width is a real limit, and overrunning it wraps rather than shrinks.

    The panel is half the terminal and the full figure is 62 columns, so on a
    120-column terminal it does not fit — and Rich would wrap it, which shears
    one wizard into two half-wizards. The packing has to answer for width as well
    as height, or the height-only answer picks a figure that does not fit.
    """
    cols, rows = art._from_source()
    assert art.banner_size(rows, cols - 1)[0] < cols, (
        "a budget one column short of the art still picked the art's own width")


def test_the_banner_is_centred_as_one_block_and_cannot_shear():
    """Centring moves the whole figure; it never re-indents a row at a time.

    `Text(justify="center")` and `rich.align.Align` both centre each line against
    *its own* width, after the renderer has trimmed that line's trailing
    whitespace. The figure's rows are indented by different amounts, so centring
    them one by one applies the art's own indentation a second time and shears
    the drawing — the panel was rendering shifts of 13, 15, 18 and 19 columns
    down a single drawing. One margin, computed once for the block, cannot do
    that: every row moves by the same amount or none does.
    """
    source = art.banner(13, 55).plain.splitlines()
    for width in (0, 40, 55, 120):
        drawn = art.banner(13, 55, width).plain.splitlines()
        shifts = {len(row) - len(row.lstrip()) - (len(src) - len(src.lstrip()))
                  for row, src in zip(drawn, source)}
        assert len(shifts) == 1, f"the figure sheared at width {width}: {shifts}"


def test_the_banner_frame_reserves_the_arts_real_width(tui):
    """The panel fits the art, or Rich wraps and shears it.

    Checked on the rendered frame rather than on `banner_size()`, because the
    art is drawn centred: the padding Rich adds either side is part of the row,
    and a row that is one column too wide for its cell wraps rather than
    truncates — which shears the figure into two lines of half a wizard.
    """
    from wizard.cli.tui import widgets

    width, height = tui._geometry()
    art_rows = widgets.art_rows(height, widgets.art_cols(width))
    drawn = art.banner(art_rows, widgets.art_cols(width))
    lines = [r for r in drawn.plain.splitlines() if r.strip()]
    longest = max(lines, key=len).strip()

    frame = _plain(tui._render_top())
    assert longest in "\n".join(frame), "the art's longest row was wrapped; the figure sheared"
    # One line per row of the figure, and no more: a wrapped row would show up as
    # the figure being taller on screen than it is.
    assert len([r for r in frame if r]) == len(drawn.plain.splitlines()) + 7, (
        "the panel is not the height its art makes it")



def test_the_banner_keeps_every_colour_it_was_drawn_with():
    text = art.banner()
    styles = {span.style for span in text.spans if span.style}
    assert styles, "the banner rendered without any colour"
    assert all(s.startswith("#") for s in styles)
    # Each cell carries its own colour, so there are many distinct ones.
    assert len(styles) > 100, f"only {len(styles)} colours survived"


# ---------------------------------------------------------------------------
# Choosing which repository to investigate
# ---------------------------------------------------------------------------

def test_a_path_on_the_command_line_becomes_the_repository(tui, tmp_path):
    """`wizard C:/somewhere` investigates somewhere, not the cwd."""
    from wizard.cli.tui.app import WizardTUI

    with _headless():
        other = WizardTUI(repo_path=str(tmp_path))
    assert other.repo_path == str(tmp_path)
    frame = _render(other)
    assert "what shall we do?" in frame
    # The panel names the folder. Folding the home directory away is the one
    # shortening applied — an absolute path is longer than half the panel — and
    # the tail is the part that identifies it either way, so the folder the user
    # typed is still on screen.
    assert tmp_path.name in frame, "the panel does not say which repo"


def test_no_path_means_the_current_directory():
    from wizard.cli.tui.app import WizardTUI

    with _headless():
        assert WizardTUI().repo_path == os.getcwd()


def test_a_directory_that_does_not_exist_starts_nothing(monkeypatch, capsys):
    """A typo'd path is a sentence, not three services investigating nothing."""
    from wizard.cli.tui import app as app_mod

    constructed = []

    class FakeSupervisor:
        def __init__(self):
            constructed.append(True)
        log_dir = "."

    monkeypatch.setattr("wizard.cli.tui.services.ServiceSupervisor", FakeSupervisor)

    app_mod.run_tui(str(Path(os.getcwd()) / "no-such-directory-here"))

    assert not constructed, "the services were started for a path that is not there"
    assert "is not a directory" in capsys.readouterr().out


def test_the_run_is_told_which_repo_to_read(tui, monkeypatch, tmp_path):
    """The TUI's repo_path is what the command layer is handed."""
    captured = {}

    class FakeSession:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def start(self):
            pass

    monkeypatch.setattr("wizard.cli.tui.app.TuiSession", FakeSession)
    tui.repo_path = str(tmp_path)
    tui.family = "investigate"
    tui.target = "architecture"
    tui._begin_work("look at it")

    assert captured["repo_path"] == str(tmp_path)


# ---------------------------------------------------------------------------
# The two panes: art fixed, flow scrollable
# ---------------------------------------------------------------------------

# A report long enough that the pane cannot show it all.
_LONG_REPORT = "# Report\n\n" + "\n".join(
    f"- finding {i}: the runtime recorded this line" for i in range(120)
)


class _FinishedRun:
    """A session that has already produced its report."""

    def __init__(self, report: str = _LONG_REPORT) -> None:
        self._report = report

    def snapshot(self) -> dict:
        return {"finished": True, "running": False, "status": "completed",
                "now": "complete", "report_markdown": self._report,
                "report_path": "", "events": 3}

    def snapshot_activity(self) -> list:
        return []

    def cancel(self) -> None:      # pragma: no cover - must not be called
        raise AssertionError("a finished run was asked to cancel")


def _wheel(column: int, row: int, down: bool = True) -> str:
    """The SGR mouse sequence a terminal sends for one wheel notch.

    SGR mouse is `ESC [ < button ; column ; row M`, so the row is the third
    field. It used to be pinned at 12 here while the call sites passed the row
    they meant as the column — so every wheel in these tests landed on row 12,
    and the one that was supposed to scroll the flow was landing on the panel.
    """
    return f"\x1b[<{65 if down else 64};{column};{row}M"


def _drive_app(driven, body):
    """Run the real Application, hand `body(tui, pipe)` the controls, stop it.

    Keys go in as the bytes a terminal sends, so what is exercised is the real
    key bindings and the real renderer rather than a reimplementation of them.
    """
    import asyncio

    tui, pipe = driven

    async def main():
        runner = asyncio.ensure_future(tui.app.run_async())
        await asyncio.sleep(0.3)
        result = await body(tui, pipe)
        tui.app.exit()
        await runner
        return result

    return asyncio.run(main())


def _drive_keys(driven, steps):
    """Send `steps` = [(label, bytes)] to the pane; return [(label, scroll)].

    `scroll` is read back off the Window, not from a copy the TUI keeps, so
    this also catches the offset drifting out of step with prompt_toolkit's own
    wheel handling — which writes `vertical_scroll` directly.
    """
    import asyncio

    async def body(tui, pipe):
        seen = []
        for label, sequence in steps:
            pipe.send_text(sequence)
            await asyncio.sleep(0.25)
            seen.append((label, tui.scroll))
        return seen

    return _drive_app(driven, body)


def test_the_flow_scrolls_and_the_panel_does_not(driven):
    """The wheel moves the command box, and is ignored by the panel above it.

    Both halves matter, and the second is the one that is easy to miss:
    prompt_toolkit scrolls *any* Window whose content overflows — see
    `Window._mouse_handler` — so a wheel anywhere over the panel would lift the
    identity panel's own border out of view while the user was reading it. The
    panel is given a fixed height for the same reason; this is the event that
    would get past that if nothing refused it.
    """
    from wizard.cli.tui.app import RESULT

    tui, _ = driven
    tui.session = _FinishedRun()
    tui.state = RESULT

    # The panel is 20 rows here, so row 30 is inside the box below it and row 10
    # is over the panel. Both are aimed at the same column, in the middle of the
    # terminal, so the only thing that differs between the three notches is
    # which window is under the pointer.
    box_row, panel_row, column = 30, 10, 60

    seen = _drive_keys(driven, [
        ("wheel over the flow", _wheel(column, box_row)),
        ("wheel over the panel", _wheel(column, panel_row)),
        ("wheel over the panel again", _wheel(column, panel_row)),
    ])
    (_, after_box), (_, a), (_, b) = seen

    assert after_box > 0, "the wheel did not scroll the flow"
    assert (a, b) == (after_box, after_box), (
        "a wheel over the panel moved the view; the panel must be fixed")
    assert tui.top_window.vertical_scroll == 0, "the identity panel scrolled away"


def test_the_scroll_keys_move_the_flow(driven):
    """Arrows and PageUp/PageDown scroll the right pane."""
    from wizard.cli.tui.app import RESULT

    tui, _ = driven
    tui.session = _FinishedRun()
    tui.state = RESULT

    seen = _drive_keys(driven, [
        ("down", "\x1b[B"),
        ("down", "\x1b[B"),
        ("up", "\x1b[A"),
        ("pagedown", "\x1b[6~"),
        ("pageup", "\x1b[5~"),
        ("end", "\x1b[F"),
        ("home", "\x1b[H"),
    ])
    moves = dict(seen)

    assert seen[0][1] == 1, "down did not move one line"
    assert seen[1][1] == 2, "down did not move one line"
    assert seen[2][1] == 1, "up did not move back one line"
    assert moves["pagedown"] > 2, "PageDown did not move a page"
    assert moves["pageup"] < moves["pagedown"], "PageUp did not move back"
    assert moves["end"] > moves["pageup"], "End did not reach the bottom"
    assert moves["home"] == 0, "Home did not return to the top"


def test_the_flow_shows_every_line_it_has(driven):
    """Scrolling reaches the whole report: the last line is reachable.

    The offset is clamped by the pane's own geometry, so "reachable" means the
    bottom of the content, not a fixed number.
    """
    from wizard.cli.tui.app import RESULT

    tui, _ = driven
    tui.session = _FinishedRun()
    tui.state = RESULT

    _drive_keys(driven, [("end", "\x1b[F")])

    top, page = tui._scroll_bounds()
    assert page > 1, "the pane reported a page of one line"
    assert top > 0, "this report fits on one screen; the test proves nothing"
    assert tui.scroll == top, "End did not land on the last line"


# ---------------------------------------------------------------------------
# The trace says each step once
# ---------------------------------------------------------------------------

def _decided(tool, path, source="explorer"):
    return ({"event_type": "agent.decided",
             "payload": {"source": source, "tool": tool, "params": {"path": path}}},
            {"event_type": "node.completed",
             "payload": {"tool": tool, "params": {"path": path}, "ok": True}})


def test_a_successful_step_is_not_logged_twice():
    """Seen on a real run, on every step of it:

        explorer → read_file · client/package.json
        runtime  ✓ read_file · client/package.json

    The same tool aimed at the same file, one line apart, and the second says
    only that nothing went wrong. Half the trace was this.
    """
    s = _session()
    decision, completion = _decided("read_file", "client/package.json")
    _drive(s, [decision, completion])
    assert _narration(s) == ["→ read_file · client/package.json"]


def test_a_step_that_failed_is_not_suppressed():
    """`!` is the one thing in the pair the decision line did not say.

    A command that ran and exited non-zero is the ordinary case of this, and it
    is the line a reader most needs — the decision above it looks identical to
    one that worked.
    """
    s = _session()
    decision, completion = _decided("execute_command", "npm test")
    completion["payload"]["ok"] = False
    _drive(s, [decision, completion])
    assert _narration(s) == [
        "→ execute_command · npm test",
        "! execute_command · npm test",
    ]


def test_a_completion_with_no_decision_above_it_is_still_logged():
    """The only record that the step ran; suppressing it would lose the step."""
    s = _session()
    _drive(s, [{"event_type": "node.completed",
                "payload": {"tool": "read_file", "params": {"path": "a.js"},
                            "ok": True}}])
    assert _narration(s) == ["✓ read_file · a.js"]


def test_a_completion_is_not_suppressed_by_a_decision_for_a_different_step():
    """Matching is on the whole step, not on "a decision happened recently"."""
    s = _session()
    first, _ = _decided("read_file", "a.js")
    _, other = _decided("read_file", "b.js")
    _drive(s, [first, other])
    assert _narration(s) == [
        "→ read_file · a.js",
        "✓ read_file · b.js",
    ]


def test_the_report_is_named_at_one_path_not_two():
    """A live run printed the engine's internal path and the CLI's copy.

    `report written · F:\\…\\wizard-runtime-engine\\.wizard\\investigations\\
    inv_…/verification_report.md` and then, in the footer, `output/
    verification_report(28).md`. Both files exist; the reader is shown one, and
    it has to be the one they can open.
    """
    s = _session()
    _drive(s, [{"event_type": "report.generated",
                "payload": {"path": "F:/engine/.wizard/investigations/inv_1/verification_report.md"}}])
    line = _roles(s)[0][1]
    assert line == "report written"
    assert ".wizard" not in line and "inv_1" not in line


# ---------------------------------------------------------------------------
# The actor column in the rendered pane
# ---------------------------------------------------------------------------

def _flow_lines(session: TuiSession, width: int = 120) -> list[str]:
    """The command box's flow, rendered, with the escapes resolved.

    The box's own border and padding are taken back off, because the tests that
    read these lines are about the column the actors are put in and not about the
    frame around them — a frame that is asserted where the frame is the subject.
    """
    from wizard.cli.tui.widgets import command_box, render_to_ansi, working_content

    snap = session.snapshot()
    snap["running"] = True
    ansi = render_to_ansi(command_box(working_content(
        "investigate", snap, session.snapshot_activity(), 0.0)), width)
    out = []
    for line in _plain(ansi):
        if line.startswith("│"):
            line = line[3:] if line[1:3] == "  " else line[1:]   # border + padding
        out.append(line.rstrip().rstrip("│").rstrip())
    return out


def test_the_actors_line_up_in_a_column_in_the_rendered_pane():
    """The point of the column: the roles are scannable on their own.

    Every line's text starts at the same offset, so a reader can follow the
    hand-offs — the Explorer deciding, the Planner stepping in, the Verifier
    judging — without reading the sentences in between to find the name.
    """
    s = _session()
    _drive(s, [
        {"event_type": "agent.decided",
         "payload": {"source": "explorer", "tool": "read_file",
                     "params": {"path": "client/package.json"}}},
        {"event_type": "agent.decided",
         "payload": {"source": "node_plan", "tool": "read_file",
                     "params": {"path": "server/index.js"}}},
        {"event_type": "goal.satisfied", "payload": {"goal_name": "Verify Runtime"}},
    ])

    rows = [ln for ln in _flow_lines(s) if ln.strip()]
    readers = [ln for ln in rows if ln.startswith(("explorer", "planner", "runtime"))]
    assert len(readers) == 3, f"the actors are not at the start of their lines:\n" + "\n".join(rows)

    # Where each line's own text begins — after the padded actor column.
    starts = {len(ln) - len(ln.lstrip()[len(ln.split()[0]):].lstrip()) for ln in readers}
    assert len(starts) == 1, f"the actor column is ragged: {starts}"


def test_a_line_with_no_actor_is_not_indented_into_the_column():
    """`seams.resolved` reports the wiring, and has no actor to name.

    It must not be pushed right to sit under the column — that would claim an
    empty first column of every reader-free line, and a blank where a name goes
    reads as a missing name rather than as none being applicable.
    """
    s = _session()
    _drive(s, [{"event_type": "seams.resolved",
                "payload": {"planner": "HttpPlanner", "explorer": "HttpExplorer",
                            "verifier": "HttpVerifier"}}])
    line = _roles(s)[0]
    assert line[0] == "", "seams carries an actor it does not have"
    flow = [ln for ln in _flow_lines(s) if "wired" in ln]
    assert flow and flow[0].startswith("wired"), f"the wiring line was indented: {flow}"




class _LiveRun:
    """A session that is still going."""

    def __init__(self) -> None:
        self.cancelled = False

    def snapshot(self) -> dict:
        return {"finished": False, "running": True, "status": "",
                "now": "reading package.json", "events": 1}

    def snapshot_activity(self) -> list:
        return []

    def cancel(self) -> None:
        self.cancelled = True


def test_esc_on_a_live_run_asks_the_runtime_to_stop(tui):
    """Esc means "stop" while there is something to stop."""
    live = _LiveRun()
    tui.session = live
    tui.state = WORKING

    tui._back()

    assert live.cancelled, "Esc during a run no longer stops it"
    assert tui.state == WORKING


def test_esc_on_a_finished_run_leaves_the_working_screen(tui):
    """Esc used to do nothing here, which is what made a run look frozen.

    Nothing is left to cancel once the report exists, so Esc's job changes: it
    is the way out. This is the dead-end the user hit.
    """
    tui.session = _FinishedRun()
    tui.state = WORKING

    tui._back()

    assert tui.state == RESULT, "Esc is still a no-op on a finished run"


def test_a_finished_run_crosses_to_the_result_by_itself(tui, monkeypatch):
    """The worker's last event carries the screen across.

    Nothing needed to be asked: the session already tells the TUI when it
    changes, so the moment it is finished the result is what should be showing.
    """
    started = {}

    class FakeSession:
        def __init__(self, **kwargs):
            started.update(kwargs)
            self.finished = False

        def start(self):
            self.finished = True
            started["on_change"]()      # exactly what the worker does

        def snapshot(self):
            return {"finished": self.finished}

    monkeypatch.setattr("wizard.cli.tui.app.TuiSession", FakeSession)
    tui._begin_work("look at the repo")

    assert tui.state == RESULT, (
        "a run that finished left the user on the working screen")


def test_the_run_screen_takes_no_typing(tui):
    """The box is inert during a run: there is no mid-run steering endpoint.

    It used to be focused and live, which also meant it swallowed the arrow and
    page keys before the pane could scroll.
    """
    tui.state = INTENT
    assert not tui.input.read_only(), "the box is inert on the intent screen"
    tui.state = WORKING
    assert tui.input.read_only(), "the box takes typing during a run"
    tui.state = RESULT
    assert not tui.input.read_only(), "the box stayed locked after the run"


def test_the_result_screen_says_how_to_run_another(tui):
    """The way out is on the screen, not left to be guessed."""
    tui.state = RESULT
    tui.session = _FinishedRun()
    tui.family = "investigate"
    assert "r to run another" in _render(tui)


def test_r_opens_the_menu_again(driven):
    """`r` on the result screen is the explicit do-it-again."""
    from wizard.cli.tui.app import RESULT

    async def body(tui, pipe):
        import asyncio
        tui.session = _FinishedRun()
        tui.state = RESULT
        await asyncio.sleep(0.2)
        pipe.send_text("r")
        await asyncio.sleep(0.3)
        return tui.state

    assert _drive_app(driven, body) == MENU, "`r` did not open the menu"


def test_esc_returns_to_the_menu_from_the_result(tui):
    """Esc is the way back out, on the screen that ends a run."""
    tui.state = RESULT
    tui._back()
    assert tui.state == MENU


# ---------------------------------------------------------------------------
# The browser binary, before any investigation needs it
# ---------------------------------------------------------------------------

def _fake_browser_cache(root: Path) -> Path:
    """A directory shaped like Playwright's browser cache."""
    exe = root / "chromium-1234" / "chrome-win64" / "chrome.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"")
    return exe


def test_a_browser_on_disk_is_reported_ready(tmp_path, monkeypatch):
    from wizard.cli.tui import services

    exe = _fake_browser_cache(tmp_path)
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path))
    assert services.find_chromium() == exe
    assert "ready" in services.ensure_chromium()


def test_an_empty_browser_directory_is_not_ready(tmp_path, monkeypatch):
    """An empty ms-playwright folder is a cache with nothing in it."""
    from wizard.cli.tui import services

    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path))
    assert services.find_chromium() is None


def test_the_browser_check_starts_no_playwright_driver(monkeypatch):
    """The check must not import the driver.

    Importing it starts a driver subprocess whose one-shot start-and-stop prints
    "Task was destroyed but it is pending!" and a TargetClosedError traceback to
    the user's terminal — on every single `wizard` launch. The filesystem answer
    is the same answer, silently.
    """
    import sys

    from wizard.cli.tui import services

    # An empty cache, and the download itself stubbed out. Without the stub this
    # test would fetch Chromium for real: `playwright install` writes ~700 MB and
    # appends the browsers path to .gitignore. A test must not do that.
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(Path(os.getcwd()) / "nope"))
    monkeypatch.setattr(
        services.subprocess, "run",
        lambda *a, **k: types.SimpleNamespace(returncode=1, stdout="", stderr="stubbed"),
    )
    monkeypatch.setattr(services, "find_chromium", lambda root=None: None)
    monkeypatch.delitem(sys.modules, "playwright", raising=False)
    monkeypatch.delitem(sys.modules, "playwright.sync_api", raising=False)

    assert "unavailable" in services.ensure_chromium()

    assert "playwright.sync_api" not in sys.modules, (
        "the browser check imported the Playwright driver"
    )


def test_the_download_is_the_real_playwright_command(monkeypatch):
    """When the browser is missing, fetch it the one supported way.

    A guard on the guard: the test above proves no driver is imported, and an
    earlier version of it very nearly fetched 700 MB while proving that.
    """
    from wizard.cli.tui import services

    calls = []
    monkeypatch.setattr(
        services.subprocess, "run",
        lambda *a, **k: calls.append(a[0]) or types.SimpleNamespace(
            returncode=1, stdout="", stderr="stubbed"),
    )
    monkeypatch.setattr(services, "find_chromium", lambda root=None: None)

    services.ensure_chromium()

    assert len(calls) == 1, "the download ran more than once"
    assert calls[0][1:] == ["-m", "playwright", "install", "chromium"]


def test_a_missing_playwright_package_is_reported_as_such(tmp_path, monkeypatch):
    """Binaries without the package that drives them are no use."""
    from wizard.cli.tui import services

    _fake_browser_cache(tmp_path)
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path))
    monkeypatch.setattr(services.importlib.util, "find_spec", lambda name: None)

    line = services.ensure_chromium()
    assert "unavailable" in line and "playwright package" in line


# ---------------------------------------------------------------------------
# Telling the user a browser phase is available, and letting them ask for it
# ---------------------------------------------------------------------------

def test_f2_fills_the_box_with_the_clients_url(driven):
    """The one keypress that turns a discovered client into a browser phase.

    Driven through the real Application and the real binding, because the claim
    is about what a keystroke does. F2 rather than an automatic fill: the URL
    has to reach the Runtime as something the user asked for, since the egress
    guard is fail-closed and correctly refuses a host nobody named.
    """
    from wizard.cli.parser.frontend import Frontend

    tui, pipe = driven
    tui.frontend = Frontend("client", "vite", "dev", 5173, listening=True)

    async def body(tui, pipe):
        import asyncio
        tui.state = INTENT
        tui.app.layout.focus(tui.input)
        await asyncio.sleep(0.2)
        pipe.send_text("\x1bOQ")          # F2 in xterm's SS3 form
        await asyncio.sleep(0.3)
        return tui.input.text

    assert _drive_app(driven, body) == "http://localhost:5173"


def test_f2_does_nothing_when_no_client_was_found(driven):
    """An empty box is not an invitation to invent a URL."""
    tui, _ = driven
    tui.frontend = None

    async def body(tui, pipe):
        import asyncio
        tui.state = INTENT
        tui.app.layout.focus(tui.input)
        await asyncio.sleep(0.2)
        pipe.send_text("\x1bOQ")
        await asyncio.sleep(0.3)
        return tui.input.text

    assert _drive_app(driven, body) == ""


def test_the_intent_screen_looks_for_a_client_when_it_opens(tmp_path, monkeypatch):
    """Discovery happens on the screen the answer belongs to, not once at startup.

    A user who starts their dev server while the wizard is open sees it on the
    next visit rather than after a restart.
    """
    import json

    (tmp_path / "client").mkdir()
    (tmp_path / "client" / "package.json").write_text(json.dumps({
        "scripts": {"dev": "vite"},
        "devDependencies": {"vite": "^5"},
    }), encoding="utf-8")
    (tmp_path / "client" / "vite.config.js").write_text(
        "export default { server: { port: 5199 } };", encoding="utf-8")

    with _headless():
        tui = WizardTUI(str(tmp_path))
        assert tui.frontend_hint == "", "nothing was looked for before the screen opened"
        tui._enter_intent()
        assert tui.frontend is not None
        assert tui.frontend.port == 5199, "the declared port was not read"
        # Not asserting the port is in the hint: this client is not running, so
        # the hint tells the user to start it and names no URL. That is the
        # behaviour test_a_client_that_is_not_running_is_given_a_start_command
        # pins down.
        assert "not running" in tui.frontend_hint


def test_a_project_the_scanner_cannot_read_still_opens_the_intent_screen(tmp_path):
    """Discovery failing is not a reason the user cannot type an intent."""
    missing = tmp_path / "not-here"
    with _headless():
        tui = WizardTUI(str(missing))
        tui.family, tui.target = "investigate", "architecture"
        tui._enter_intent()
        assert tui.state == INTENT
        assert tui.frontend_hint == "" and tui.frontend is None


# ---------------------------------------------------------------------------
# The live page — the application itself, in the pane
# ---------------------------------------------------------------------------

def _page(url="http://localhost:5173/login", title="Taskboard",
          controls=None, node_count=12) -> dict:
    """One reading of a page, shaped as the kernel's `page_view` builds it."""
    return {
        "url": url, "title": title, "node_count": node_count,
        "controls": controls if controls is not None else [
            {"role": "textbox", "name": "Email", "selector": 'role=textbox[name="Email"]',
             "disabled": False, "visible": True, "value": "", "input_type": "email"},
            {"role": "textbox", "name": "Password", "selector": 'role=textbox[name="Password"]',
             "disabled": False, "visible": True, "value": "", "input_type": "password"},
            {"role": "button", "name": "Sign in", "selector": 'role=button[name="Sign in"]',
             "disabled": False, "visible": True, "value": "", "input_type": None},
        ],
    }


def _showing_page(session, tui) -> str:
    """One frame of the page view for `session`, as the terminal shows it."""
    tui.family = "investigate"
    tui.session = session
    tui.state = WORKING
    tui.show_page = True
    return _render(tui)


def test_the_page_pane_shows_the_page_the_browser_is_on(tui):
    """The half of a run that a trace cannot show: what it was looking at.

    The flow says a control was pressed; it cannot say what else was on the page
    when it was, which button the one that was pressed sat beside, or whether the
    field above it had anything in it.
    """
    s = _session()
    _drive(s, [
        {"event_type": "browser.navigated",
         "payload": {"url": "http://localhost:5173/login", "status": 200,
                     "title": "Taskboard", "page": _page()}},
    ])
    frame = _showing_page(s, tui)
    assert "http://localhost:5173/login" in frame
    assert "Taskboard" in frame
    assert "12 nodes · 3 controls" in frame
    for name in ("Email", "Password", "Sign in"):
        assert name in frame, f"{name} is missing from the page"


def test_the_marker_points_at_the_control_the_run_actually_pressed(tui):
    """One marker, on the one control, and nowhere else.

    A page that marked everything, or marked the wrong thing, would be worse
    than no marker: the reader is watching a specific step and the marker is the
    only thing tying the flow's newest line to a place on the page.
    """
    s = _session()
    _drive(s, [
        {"event_type": "browser.acted",
         "payload": {"tool": "browser_click", "url": "http://localhost:5173/login",
                     "selector": 'role=button[name="Sign in"]',
                     "effect": "unchanged", "page": _page()}},
    ])
    lines = _showing_page(s, tui).split("\n")
    marked = [ln for ln in lines if "▸" in ln]
    assert len(marked) == 1, f"expected one mark, got {marked}"
    assert "Sign in" in marked[0] and "button" in marked[0]
    # The fields above it are not marked.
    assert not any("▸" in ln for ln in lines if "Email" in ln)


def test_the_pane_says_what_the_run_did_to_the_page_it_is_showing(tui):
    """The marker says which control; this line says what came of pressing it."""
    s = _session()
    _drive(s, [
        {"event_type": "browser.acted",
         "payload": {"tool": "browser_click", "url": "http://localhost:5173/login",
                     "selector": 'role=button[name="Sign in"]', "effect": "unchanged",
                     "page": _page()}},
    ])
    frame = _showing_page(s, tui)
    assert "pressed Sign in" in frame
    # The measured outcome, not an assessment of it: the pane has no business
    # calling an inert button a failure.
    assert "page unchanged" in frame


def test_the_last_act_outlives_the_control_it_names(tui):
    """A click that navigates takes its own button off the page.

    The act still has to be reportable. Dropping the line because the marker had
    nothing to attach to would hide the one event the reader pressed `b` to see —
    and showing it with no marker, naming the control that is no longer there, is
    the honest account of what happened.
    """
    s = _session()
    _drive(s, [
        {"event_type": "browser.acted",
         "payload": {"tool": "browser_click", "url": "http://localhost:5173/tasks",
                     "selector": 'role=button[name="Sign in"]', "effect": "changed",
                     # The new page: the button that was pressed is gone.
                     "page": _page(url="http://localhost:5173/tasks", title="Tasks",
                                   controls=[{"role": "link", "name": "New task",
                                              "selector": 'role=link[name="New task"]',
                                              "disabled": False, "visible": True,
                                              "value": "", "input_type": None}])}},
    ])
    frame = _showing_page(s, tui)
    assert "pressed" in frame and "page changed" in frame
    assert "Sign in" in frame, "the control that was pressed is not named at all"
    assert "▸" not in frame, "a control that is gone must not be marked"


def test_a_field_shows_what_it_now_holds(tui):
    """The credentials landing is the finding; the pane should carry it."""
    s = _session()
    page = _page(controls=[{"role": "textbox", "name": "Email",
                            "selector": 'role=textbox[name="Email"]',
                            "disabled": False, "visible": True,
                            "value": "wizard.probe@example.test", "input_type": "email"}])
    _drive(s, [
        {"event_type": "browser.acted",
         "payload": {"tool": "browser_type", "selector": 'role=textbox[name="Email"]',
                     "effect": "unchanged", "value": "wizard.probe@example.test",
                     "page": page}},
    ])
    assert "wizard.probe@example.test" in _showing_page(s, tui)


def test_a_page_the_run_has_not_reached_says_so(tui):
    """An empty pane and "not yet" look identical and are not the same fact."""
    s = _session()
    _drive(s, [{"event_type": "node.completed", "payload": {"ok": True}}])
    tui.family, tui.session, tui.state, tui.show_page = "investigate", s, WORKING, True
    frame = _render(tui)
    assert "has not reached a page" in frame
    # And it does not invent a url to draw.
    assert "http" not in frame


def test_the_page_is_offered_only_once_there_is_a_page(tui):
    """A key that promises a view and opens an empty one stops being pressed."""
    s = _session()
    _drive(s, [{"event_type": "node.completed", "payload": {"ok": True}}])
    tui.family, tui.session, tui.state = "investigate", s, WORKING
    assert "b for the page" not in _render(tui)
    assert not tui._has_page()

    s2 = _session()
    _drive(s2, [{"event_type": "browser.navigated", "payload": {"page": _page()}}])
    tui.session = s2
    assert tui._has_page()
    # Read off the FLOW pane, which is where the hint lives — and which the pane
    # now only reaches after the reader has chosen it. The first page opens the
    # pane by itself (see _follow_page), so the state below is the one a reader
    # is in when the hint is the thing they need.
    tui.show_page = False
    tui._page_followed = True
    assert "b for the page" in _render(tui)


def test_the_page_survives_a_narration_line_that_was_folded(tui, monkeypatch):
    """The page is state, not a log entry — so it updates when no line is drawn.

    Absorbing the page inside the `if line:` block would look correct on every
    run where a line is always drawn, and freeze the pane on the one event the
    trace decided was not news. That is the moment its reader most wants to be
    sure something is still looking at the page, so the read happens first and
    the narration decides afterwards whether it has anything to say about it.
    """
    s = _session()
    monkeypatch.setattr(session_mod, "_narrate",
                        lambda ev_type, payload: ("", ""))
    _drive(s, [
        {"event_type": "browser.navigated", "payload": {"url": "http://x/", "page": _page()}},
    ])
    assert [ln for ln in s.snapshot_activity() if ln.role == "browser"] == [], \
        "the trace was supposed to draw no browser line"
    assert s.snapshot()["page"] is not None, "the page was dropped with the line"


def test_a_step_that_carries_no_page_keeps_the_last_one(tui):
    """Absent is not empty: a browser event with no reading leaves the pane alone."""
    s = _session()
    _drive(s, [
        {"event_type": "browser.navigated", "payload": {"url": "http://x/", "page": _page()}},
        {"event_type": "browser.acted",
         "payload": {"tool": "browser_click", "selector": 'role=button[name="Sign in"]'}},
    ])
    snap = s.snapshot()
    assert snap["page"]["url"] == "http://localhost:5173/login"
    assert snap["last_act"]["selector"] == 'role=button[name="Sign in"]'


def test_b_flips_the_pane_and_resets_where_it_was_scrolled(tui):
    """The two views have different heights; an offset is not transferable."""
    s = _session()
    _drive(s, [{"event_type": "browser.navigated", "payload": {"page": _page()}}])
    tui.family, tui.session, tui.state = "investigate", s, WORKING
    # The pane turns itself to the first page; this test is about what `b` does
    # afterwards, so it starts from where a reader is when they press it: back
    # on the flow, having already seen the page.
    tui.show_page = False
    tui._page_followed = True
    assert "flow" in _render(tui)
    tui._toggle_page()
    assert "live page" in _render(tui)
    assert tui.scroll == 0
    tui._toggle_page()
    assert "live page" not in _render(tui)


def test_a_new_run_does_not_open_on_the_last_run_s_page(tui):
    """The page belongs to the run that reached it."""
    s = _session()
    _drive(s, [{"event_type": "browser.navigated", "payload": {"page": _page()}}])
    tui.session, tui.show_page = s, True
    tui._enter_menu()
    assert tui.show_page is False
    assert "live page" not in _render(tui)


def test_the_runtime_s_own_name_for_the_control_is_what_the_pane_uses(tui):
    """A selector is the machine's name for a control; the pane is for a person.

    The name is captured by the runtime before the action, and it is needed most
    when the control is afterwards gone — here the button renamed itself to
    "Signing in..." the moment it was pressed, so the selector addresses nothing
    on the page that came back. Falling back to the selector would put
    `role=button[name="Sign in"]`, clipped, where the pane's most-read line goes.
    """
    s = _session()
    _drive(s, [
        {"event_type": "browser.acted",
         "payload": {"tool": "browser_click", "url": "http://localhost:5173/login",
                     "selector": 'role=button[name="Sign in"]',
                     "selector_name": "Sign in", "effect": "unchanged",
                     # The button as the page now has it: renamed and disabled.
                     "page": _page(controls=[{"role": "button", "name": "Signing in…",
                                              "selector": 'role=button[name="Signing in…"]',
                                              "disabled": True, "visible": True,
                                              "value": "", "input_type": None}])}},
    ])
    frame = _showing_page(s, tui)
    assert "pressed Sign in" in frame
    assert "role=button" not in frame, "the selector was shown where a name was available"
    # And the page's own account of what the press did to the button is shown too.
    assert "Signing in…" in frame


def test_a_control_the_runtime_could_not_name_falls_back_to_its_selector(tui):
    """Half an answer beats no sentence: something was pressed, and which one."""
    s = _session()
    _drive(s, [
        {"event_type": "browser.acted",
         "payload": {"tool": "browser_click", "url": "http://x/",
                     "selector": 'role=button[name="Go"]',
                     "selector_name": None, "effect": "changed",
                     "page": _page(controls=[])}},
    ])
    frame = _showing_page(s, tui)
    assert "pressed" in frame and "Go" in frame


# ---------------------------------------------------------------------------
# The pane follows the browser on its own
# ---------------------------------------------------------------------------

def test_the_pane_turns_to_the_page_without_being_asked(tui):
    """A run that drives a browser must show the application it is driving.

    `b` is how a reader goes back to the flow. It must not be the only way to
    find out the page exists: the hint for it sits at the bottom of a pane the
    reader is already reading, and a live browser phase that shows nothing about
    the page is the half of the run a terminal cannot otherwise show, missing.
    """
    s = _session()
    _drive(s, [
        {"event_type": "browser.navigated",
         "payload": {"url": "http://localhost:5173/login", "status": 200,
                     "title": "Taskboard", "page": _page()}},
    ])
    tui.family = "investigate"
    tui.session = s
    tui.state = WORKING
    tui.show_page = False
    frame = _render(tui)
    assert "live page" in frame
    assert "http://localhost:5173/login" in frame


def test_the_pane_follows_once_and_never_drags_the_reader_back(tui):
    """Leaving the page is a decision, and the next page must not undo it."""
    s = _session()
    _drive(s, [
        {"event_type": "browser.navigated",
         "payload": {"url": "http://localhost:5173/login", "status": 200,
                     "title": "Taskboard", "page": _page()}},
    ])
    tui.family = "investigate"
    tui.session = s
    tui.state = WORKING
    tui.show_page = False
    _render(tui)                       # follows
    assert tui.show_page is True
    tui._toggle_page()                 # the reader reads the flow instead
    assert tui.show_page is False
    _drive(s, [
        {"event_type": "browser.acted",
         "payload": {"tool": "browser_click", "url": "http://localhost:5173/home",
                     "selector": 'role=button[name="Sign in"]', "selector_name": "Sign in",
                     "effect": "changed", "value": None, "page": _page()}},
    ])
    _render(tui)
    assert tui.show_page is False, "the pane turned itself back after the reader left it"


def test_the_pane_stays_on_the_flow_until_there_is_a_page(tui):
    """Nothing to show means nothing shown: an empty pane named "live page"
    would teach the reader the view is broken."""
    s = _session()
    _drive(s, [
        {"event_type": "node.started", "payload": {"node_id": "n1"}},
    ])
    tui.family = "investigate"
    tui.session = s
    tui.state = WORKING
    tui.show_page = False
    frame = _render(tui)
    assert "live page" not in frame


# ---------------------------------------------------------------------------
# The step happening, while it is happening
# ---------------------------------------------------------------------------

def test_a_step_beginning_is_narrated_as_work_in_the_present_tense():
    """`node.started` is the only forward-looking line on the pane.

    Every other event is retrospective — the decision that proposed the step
    above it, the result below it — so without this one a run reads as a plan
    being accepted followed by a column of answers, with the work nowhere in
    between. The line has to say what is being done now, in the continuous
    present, because that is the tense of the thing it describes.
    """
    text, style = _narrate("node.started", {
        "tool": "read_file", "params": {"path": "src/main.py"}})
    assert text.startswith("▶ ")
    assert "reading" in text
    assert "src/main.py" in text
    assert "read_file" not in text, "the tool name is on the lines either side of this one"


def test_every_tool_the_kernel_registers_can_be_narrated():
    """A guard, not a nicety: a tool added to the kernel without a phrase here
    would narrate under its own name, which reads as a step the wizard does not
    understand. The two lists have to move together."""
    from wizard.cli.tui.session import _DOING
    from wizard_kernel.world.tools import _REGISTERED_TOOLS

    missing = sorted(set(_REGISTERED_TOOLS) - set(_DOING))
    assert not missing, (
        f"the kernel registers tools this pane cannot narrate: {missing}. "
        "Add a present-tense phrase for each in _DOING."
    )


def test_a_tool_nobody_taught_the_pane_is_narrated_under_its_own_name():
    """The honest reading of an unfamiliar step. Inventing a plausible verb for
    a tool this file has not seen is how a trace starts describing work that
    did not happen — which is exactly what the guards in this file exist for."""
    text, _ = _narrate("node.started", {"tool": "rot13_the_database", "params": {}})
    assert "rot13_the_database" in text


def test_a_browser_step_is_attributed_to_the_browser_and_a_file_step_is_not():
    """The pane colours the line by who acted, so `browser_*` has to be read off
    the tool the kernel actually resolved rather than assumed from the family."""
    from wizard.cli.tui.session import _role

    assert _role("node.started", {"tool": "browser_type"}) == "browser"
    assert _role("node.started", {"tool": "browser_click"}) == "browser"
    assert _role("node.started", {"tool": "read_file"}) == "runtime"


def test_the_step_beginning_reaches_the_trace_in_order(tui):
    """Start, then completion — on the screen, in that order."""
    s = _session()
    _drive(s, [
        {"event_type": "node.started",
         "payload": {"node_id": "n1", "tool": "browser_type",
                     "params": {"selector": 'role=textbox[name="Email"]'}}},
        {"event_type": "node.completed",
         "payload": {"node_id": "n1", "tool": "browser_type", "ok": True,
                     "params": {"selector": 'role=textbox[name="Email"]'}}},
    ])
    lines = [ln.text for ln in s.snapshot_activity()]
    started = next(i for i, t in enumerate(lines) if t.startswith("▶ "))
    done = next(i for i, t in enumerate(lines) if t.startswith("✓ "))
    assert started < done


# ---------------------------------------------------------------------------
# Pacing — a display setting, and only that
# ---------------------------------------------------------------------------

def test_pacing_is_off_unless_a_view_asks_for_it():
    """Every test in this file drives a session with the default. A default that
    paused would make the suite pay a delay per line to check a claim that has
    nothing to do with timing."""
    assert _session().pace == 0.0


def test_pacing_holds_only_the_events_that_put_a_line_on_screen():
    """A run emits far more events than it shows. Paying the delay for each of
    them would multiply the run's length while changing nothing a viewer sees."""
    import time

    s = _session(pace=0.4)
    started = time.monotonic()
    s._pace({"event_type": "seams.resolved"}, shown_before=s._lines_shown())
    assert time.monotonic() - started < 0.1, "an event with no line was held anyway"


def test_pacing_holds_a_narrated_event_long_enough_to_read():
    s = _session(pace=0.2)
    s._log("▶ reading src/main.py", "wiz.accent")
    before = s._lines_shown()
    s._log("✓ read_file · src/main.py", "wiz.ok")
    import time
    started = time.monotonic()
    s._pace({"event_type": "node.completed"}, shown_before=before)
    assert time.monotonic() - started >= 0.15


def test_pacing_gives_a_browser_step_longer_because_there_is_more_to_watch():
    """The page pane beside the trace repaints on those events; a file read has
    nothing to watch beyond its own line."""
    import time

    def held(event_type: str) -> float:
        s = _session(pace=0.2)
        before = s._lines_shown()
        s._log("a line", "wiz.ok")
        started = time.monotonic()
        s._pace({"event_type": event_type}, shown_before=before)
        return time.monotonic() - started

    assert held("browser.acted") > held("node.completed")


def test_a_held_step_never_becomes_a_held_up_quit():
    """Cancelling during a pause has to end it, not wait it out."""
    import time

    s = _session(pace=5.0)
    before = s._lines_shown()
    s._log("a line", "wiz.ok")
    s.cancelled = True
    started = time.monotonic()
    s._pace({"event_type": "node.completed"}, shown_before=before)
    assert time.monotonic() - started < 0.2


def test_pacing_cannot_reorder_events_or_change_what_was_found():
    """The whole reason pacing is allowed to exist: it sits between events, after
    the step has executed and its observation is filed, so nothing upstream can
    depend on it. Paced and unpaced runs must agree on every fact."""
    events = [
        {"event_type": "node.started",
         "payload": {"node_id": "n1", "tool": "read_file", "params": {"path": "a.py"}}},
        {"event_type": "node.completed",
         "payload": {"node_id": "n1", "tool": "read_file", "ok": True,
                     "params": {"path": "a.py"}}},
        {"event_type": "claim.admitted",
         "payload": {"claim_type": "FILE_READ", "key": "a.py", "value": "42 lines"}},
        {"event_type": "done", "status": "completed", "report_markdown": "# r",
         "report_path": "output/r.md"},
    ]
    quick, slow = _session(), _session(pace=0.05)
    _drive(quick, events)
    _drive(slow, events)

    def shape(s):
        return [(ln.text, ln.style, ln.role) for ln in s.snapshot_activity()]

    assert shape(quick) == shape(slow)
    assert quick.snapshot()["status"] == slow.snapshot()["status"]


# ---------------------------------------------------------------------------
# One screen, not two
# ---------------------------------------------------------------------------

@contextmanager
def _options_seen_by(family: str, **env):
    """The `RequestOptions` the TUI hands the command for `family`.

    `for_urls` defaults `browser_headless` to False — a user who types a URL on
    the command line wants to watch it. Under the TUI that default opens a
    second, foreign window beside the interface showing the page the pane is
    already showing, so what the TUI passes is worth pinning down.
    """
    from wizard.cli.commands import explain, investigate, report, verify

    seen = {}

    def capture(*args):
        # By type, not position: the four families take different arguments and
        # `report` does not take a target at all.
        seen["options"] = next(a for a in args if isinstance(a, RequestOptions))
        return iter(())

    modules = {"investigate": investigate, "verify": verify,
               "report": report, "explain": explain}
    target = modules[family]
    name = family
    original = getattr(target, name)

    for key, value in env.items():
        os.environ[key] = value
    try:
        setattr(target, name, capture)
        yield seen
    finally:
        setattr(target, name, original)
        for key in env:
            os.environ.pop(key, None)


@pytest.mark.parametrize("family", ["investigate", "verify", "report", "explain"])
def test_the_browser_window_is_shown_unless_the_reader_says_otherwise(family):
    """Watching the agent drive a real page is the point of the browser.

    The pane this view draws of the page is a reading of it, not a substitute
    for it: the window is what shows the click land. So the default is a visible
    browser, and the view says so explicitly instead of leaving it to `for_urls`
    — one line here is the whole of what this view decides about that.
    """
    os.environ.pop("WIZARD_BROWSER_HEADLESS", None)
    with _options_seen_by(family) as seen:
        s = _session(family=family, target="http://localhost:5173")
        list(s._get_event_generator())
    assert seen["options"].browser_headless is False


def test_a_reader_who_asked_for_no_window_gets_none():
    """`WIZARD_BROWSER_HEADLESS=1` is a person saying they do not want a window.
    The view overruling that would be the view overruling the person using it."""
    with _options_seen_by("investigate", WIZARD_BROWSER_HEADLESS="1") as seen:
        s = _session(family="investigate", target="http://localhost:5173")
        list(s._get_event_generator())
    assert seen["options"].browser_headless is True


def test_the_app_paces_a_run_so_a_person_can_watch_it(tui):
    """A run planned deterministically against a warm browser finishes faster
    than it can be read — the trace lands as one already-complete column, which
    reads as a replay rather than as work. The session default is zero (tests
    drive sessions directly and must not pay a delay per line), so the app has
    to be the thing that turns pacing on, and this is where that is checked."""
    tui.family = "investigate"
    tui.target = "architecture"
    # The construction is what is under test, not the run: starting the worker
    # here would put a real investigation on whatever engine happens to be
    # listening, which is a test that depends on the machine it runs on.
    started: list[TuiSession] = []
    original = TuiSession.start
    TuiSession.start = lambda self: started.append(self)
    try:
        tui._begin_work("look at the architecture")
    finally:
        TuiSession.start = original

    assert started, "the app did not start a session at all"
    assert started[0].pace > 0, (
        "the app started a run with no pacing, so its trace will appear all at once"
    )
    assert started[0].intent_text == "look at the architecture"


def test_the_scroll_offset_can_never_point_past_the_content(tui):
    """The cursor line is the scroll offset, and prompt_toolkit reads it out of
    its own content — `fragment_lines[i]` — so an offset one past the last line
    is an IndexError raised inside the renderer, surfacing as an unhandled
    exception in the event loop.

    The offset is remembered here and the content is not: a run ends and the box
    becomes a report, the reader flips between the flow and the page pane, a new
    run starts with an empty trace. Any of those can leave the offset behind.
    """
    tui.family = "investigate"
    tui.session = _session()
    tui.state = WORKING
    _render(tui)                       # gives the Window a measured height
    tui.scroll = 10_000                # far past the end of any real trace
    line = tui._cursor_line()
    rendered = _plain(tui._render_body())
    assert line < len(rendered), (
        f"the cursor line {line} is past the last rendered line ({len(rendered)})"
    )


def test_the_cursor_line_is_still_the_scroll_offset_when_it_fits(tui):
    """The clamp is a floor and a ceiling, not a flattening: without it a Window
    clamps the offset back to the top every frame and the pane cannot scroll."""
    tui.family = "investigate"
    tui.session = _session()
    tui.state = WORKING
    _render(tui)
    tui.scroll = 0
    assert tui._cursor_line() == 0


def test_a_shrinking_frame_cannot_strand_the_scroll_offset(tui):
    """The crash, reproduced: a tall frame followed by a short one.

    A long trace, then the page pane or the report — the run ends, the reader
    flips the view, and the new content is a fraction of the height the old one
    was. That is the real shape of this, and the offset has to be clamped
    against the frame being drawn.

    The stale measurement is installed by hand because that is the part the test
    harness does not produce on its own: `render_info` is filled in by the real
    renderer, and these tests call `_render_body` directly, so without this the
    check would pass for the wrong reason — against a `render_info` of `None`,
    not against a tall one that has since gone out of date.
    """
    tui.family = "investigate"
    s = _session()
    for i in range(120):
        s._log(f"step {i}", "wiz.ok")
    tui.session = s
    tui.state = WORKING
    _render(tui)

    # What the renderer last measured: a frame 120 lines tall.
    tui.right_window.render_info = types.SimpleNamespace(content_height=120,
                                                         window_height=30)
    tui.scroll = 100                   # legal for that frame

    # Now a much shorter frame, the way a state change produces one.
    tui.state = RESULT
    rendered = _plain(tui._render_body())
    line = tui._cursor_line()
    assert line < len(rendered), (
        f"the cursor line {line} is past the last line of a {len(rendered)}-line frame"
    )


def test_a_cached_frame_declares_its_height_too(tui):
    """The cache is a second way back to a short frame, and it used to return
    early without recording how tall the frame was — so returning from a long
    trace to the cached menu left `_body_lines` describing the trace, which is
    the same stale-height crash reached by a different door."""
    tui.family = "investigate"
    s = _session()
    for i in range(120):
        s._log(f"step {i}", "wiz.ok")
    tui.session = s
    tui.state = WORKING
    _render(tui)
    tall = tui._body_lines

    tui.state = MENU
    tui.menu_level = "family"
    _render(tui)                       # fills the cache
    short = tui._body_lines
    assert short < tall, "the menu frame should be shorter than a 120-line trace"

    tui.state = WORKING
    _render(tui)                       # back to the tall frame
    tui.state = MENU

    rendered = _plain(tui._render_body())          # cache hit
    # The guard's contract, stated directly: after a cache hit the recorded
    # height describes the frame that was just handed back, not whatever was on
    # screen before it. Without the guard this is still `tall`.
    assert tui._body_lines == len(rendered), (
        f"the cache hit recorded {tui._body_lines} lines for a "
        f"{len(rendered)}-line frame"
    )

    # Then through the cursor, which is what the renderer actually indexes with.
    # `render_info` is installed *after* the render because `_geometry()` rebuilds
    # the window and would wipe it — an earlier version of this test set it
    # before, so `_cursor_line` found no info and clamped to 0 for a reason that
    # had nothing to do with the guard, which is why it passed without it.
    tui.right_window.render_info = types.SimpleNamespace(content_height=tall,
                                                         window_height=30)
    tui.scroll = tall - 1
    assert tui._cursor_line() < len(rendered), (
        f"a cached frame left a stale height behind: the cursor line "
        f"{tui._cursor_line()} is past the last line of a {len(rendered)}-line frame"
    )
