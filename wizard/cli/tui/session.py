"""TuiSession — the shared state the TUI renders and the worker mutates.

One session per run. The main (prompt_toolkit) thread only ever *reads*
snapshots; a single background worker thread drives the command generator and
*writes* them. All shared mutation goes through `_lock`, and every write calls
the injected `on_change` callback so the app can `invalidate()` and redraw.

Everything shown here comes from the Runtime's own event stream. There is no
simulated path and no fabricated metric: if the Runtime is unreachable, or the
Runtime refuses the request, the reason it gave is what gets displayed. An
earlier version of this file invented a plausible-looking sequence of steps and
a synthetic token/dollar meter to fill the screen when the engine was down,
which meant a broken run and a working run looked alike. They must not: the
whole point of the tool is telling you what actually happened.

The narration covers the events the kernel really emits (session/events.py, plus
`context_supplied` from the Context Engine's audit in context/audit.py — a run
of the full stack produces it several times). `investigation.state_changed` is
defined in events.py but never fired by any code path, so nothing waits on it.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Iterator

from wizard.cli.models.investigation_request import RequestOptions

# Longest Planner rationale appended to a decision line, in characters. The
# pane is around 70 columns and the line already carries the agent and the tool;
# past this the rationale wraps the flow onto a second row every time.
_REASON_MAX = 28

# How much of the flow a reader can scroll back through. Bounded so a runaway
# run cannot grow the pane's input without limit; far larger than one screen,
# because the point of the pane is that it scrolls.
_ACTIVITY_WINDOW = 500

# Longest action subject shown on a decision line. The pane is around 70 columns
# and the line already carries the arrow, the tool and the rationale; a deeper
# path than this pushes the whole flow onto a second row.
_SUBJECT_MAX = 44


@dataclass
class LogLine:
    """One narration line in the working view."""

    text: str
    style: str  # a wiz.* style name
    # "step" or "evidence". The pane shows the loop — decisions, commands,
    # goal closures, verdicts — and a busy run admits one claim per observation,
    # so evidence quickly outnumbers the story it came from and buries it. The
    # lines are all still here and all still in the report; the pane just shows
    # a few of the evidence ones and counts the rest, because "found evidence ·
    # EXECUTION → execute_command_exit_code" is the report's business, not the
    # running commentary's.
    kind: str = "step"
    # Who did this — the half of a trace the reader is actually watching for.
    # "→ read_file · client/package.json" says a file was read and never says
    # whether the Planner had planned that read or the Explorer chose it in
    # response to what the last read found, which is the difference between a
    # script being followed and an investigation happening. Rendered as its own
    # aligned column so the roles can be scanned down rather than picked out of
    # the middle of every line. "" for a line with no single actor (the seam
    # report, which describes the wiring rather than a step).
    role: str = ""


@dataclass
class TuiSession:
    """Thread-safe state for a single run."""

    family: str                   # investigate | verify | report | explain
    target: str | None            # e.g. "architecture"; None for report
    intent_text: str = ""         # the user's free text, parsed by the command
    repo_path: str = ""
    on_change: Callable[[], None] = lambda: None

    # --- worker/runtime state (guarded by _lock) ---
    running: bool = False
    finished: bool = False
    cancelled: bool = False
    status: str = "pending"       # pending|running|completed|failed|engine_unavailable
    report_markdown: str = ""
    report_path: str = ""
    activity: list[LogLine] = field(default_factory=list)
    now: str = ""                 # the latest real step — what it is doing
    nexts: list[str] = field(default_factory=list)  # the Runtime's own next steps
    started_at: float = field(default_factory=time.monotonic)
    # The Runtime's id for this run, once it has accepted the request. Public
    # because cancelling needs it: the cancel endpoint is addressed by id, and
    # an investigation with no id has nothing upstream to stop.
    investigation_id: str = ""
    # The shape of the last context packet announced for each agent: its section
    # ids and whether it came from cache. The audit is real and worth keeping,
    # but the Runtime supplies the same eight sections to the Explorer for every
    # node of a run, so a real eleven-node run printed "8 context sections to
    # explorer" eleven times — always separated by the read it preceded, so never
    # adjacent, so never folded. It was the single loudest line on a screen meant
    # for watching work happen, and after the first it said only that nothing had
    # changed. What is tracked here is what would make it news.
    _context_seen: dict[str, tuple[tuple[str, ...], bool]] = field(default_factory=dict)
    # The last decision line logged, so the completion that follows it can tell
    # whether it is restating it. See `_is_echo`.
    _last_decision: str = ""
    # Every (claim type, key, value) the trace has already shown, so a claim
    # re-observed after a browser step is not logged again. See `_is_repeat_claim`.
    _claims_seen: set[tuple] = field(default_factory=set)
    # The browser's own reading of the page it is on: url, title, node count and
    # every control, as the kernel last saw it. Replaced wholesale on each browser
    # step and never merged — it is a picture of one moment, and merging two of
    # them would compose a page the browser was never on. None until the run
    # reaches a page at all, which is what lets the pane say "no page yet" rather
    # than draw an empty one.
    page: dict | None = None
    # Seconds to hold between narrated steps, so a run can be watched.
    #
    # A run driven by a deterministic planner and a warm browser executes far
    # faster than a person reads: eleven nodes land in well under a second and
    # the trace arrives as one already-finished column. Nothing about the run is
    # wrong when that happens — which is the problem. It *looks* wrong. A screen
    # that fills instantly reads as a recording or a mock, and the reader has no
    # chance to see which step touched which control, which is the entire reason
    # to watch a run instead of reading its report.
    #
    # This is a display setting and ONLY that. It is applied in `_run` between
    # events, after the work is already done and the observation already filed;
    # it cannot reorder events, change an outcome, or delay anything upstream.
    # Setting it to 0 makes the run exactly as fast as it ever was, which is what
    # every test does.
    pace: float = 0.0
    # The last control the run touched and what came of it, kept beside `page`
    # rather than inside it: the page is every control, and this is the one the
    # reader wants pointed at. See `_absorb_browser`.
    last_act: dict | None = None

    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _thread: "threading.Thread | None" = field(default=None, repr=False)

    # ------------------------------------------------------------------
    # Derived read helpers (take the lock, return snapshots)
    # ------------------------------------------------------------------
    def snapshot_activity(self, last: int = _ACTIVITY_WINDOW) -> list[LogLine]:
        """The flow, newest last.

        The window is wide because the working pane scrolls: it needs the lines
        to scroll *to*. It used to hand over the last 14, which was enough when
        the pane could only show its last screenful, and is not enough now — the
        pane caps the evidence lines it displays, and capping a window that had
        already thrown most of them away would leave the steps behind them
        unreachable rather than merely hidden.
        """
        with self._lock:
            return list(self.activity[-last:])

    def snapshot(self) -> dict:
        """A consistent read of the scalar fields under one lock acquisition.

        `page` and `last_act` are handed over by reference, not copied. They are
        replaced whole on every browser step and never mutated in place, so the
        reference a viewer holds is always some page the browser was actually on
        — just possibly not the newest one — and never a half-updated mixture.
        Copying them would mean duplicating up to sixty control dicts on every
        frame of a twelve-a-second redraw, to protect against a mutation that
        does not happen.
        """
        with self._lock:
            return {
                "running": self.running,
                "finished": self.finished,
                "cancelled": self.cancelled,
                "status": self.status,
                "report_markdown": self.report_markdown,
                "report_path": self.report_path,
                "now": self.now,
                "nexts": list(self.nexts),
                "started_at": self.started_at,
                "page": self.page,
                "last_act": self.last_act,
            }

    # ------------------------------------------------------------------
    # Worker lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        """Spawn the background worker that streams runtime events."""
        if self._thread is not None:
            return
        with self._lock:
            self.running = True
            self.status = "running"
            self.started_at = time.monotonic()
        self._thread = threading.Thread(target=self._run, name="wiz-worker", daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        """Ask the Runtime to stop, and stop listening.

        The Runtime has a cancel endpoint, so this is a real cancellation rather
        than a local "stop drawing" — without the call the investigation would
        carry on spending budget and emitting events nobody will read.

        The endpoint answers whether the investigation actually stopped, which
        is not the same question as whether the request arrived: a cancel that
        reaches a run which has already finished leaves it completed. Since the
        whole point of this tool is telling you what actually happened, the line
        it reports says which of the two it was.
        """
        with self._lock:
            if self.finished or self.cancelled:
                return
            self.cancelled = True
            self.now = ""
            inv_id = self.investigation_id

        stopped = False
        if inv_id:
            try:
                from wizard.cli.runtime_client.client import cancel_investigation

                stopped = cancel_investigation(inv_id)
            except Exception:  # noqa: BLE001 — the run is over either way
                stopped = False

        if not inv_id:
            # No id: the Runtime had not accepted the request yet, so there is
            # nothing upstream to stop. Claiming otherwise would be a guess.
            self._log("cancelled before the runtime accepted it", "wiz.warn")
        elif stopped:
            self._log(f"cancelled {inv_id} — the runtime stopped it", "wiz.warn")
        else:
            self._log(f"cancelled {inv_id} — asked the runtime to stop", "wiz.warn")
        self._settle("cancelled")

    def _get_event_generator(self) -> Iterator[dict]:
        """The command generator for this family, with the user's intent.

        Imported here rather than at module scope: the command modules pull in
        the whole request pipeline, and the TUI owns the screen the moment this
        module is imported.
        """
        from wizard.cli.commands import explain, investigate, report, verify

        repo = self.repo_path or os.getcwd()
        # from_env, not a bare RequestOptions(): the Runtime takes its planner
        # and agent endpoints from these options, so the default has to be the
        # environment's — which `run_tui` fills in — or a wired run silently
        # degrades to an offline one.
        options = RequestOptions.from_env()

        # The browser window is the point: a reader who watches the agent work
        # wants to see the page it is driving, not only the pane this view draws
        # of it. So the visible window is the default here.
        #
        # Stated explicitly rather than left to `for_urls` so that the one place
        # this view decides what the browser does is readable in one line, and so
        # that `WIZARD_BROWSER_HEADLESS=1` — a user asking for no window at all —
        # is honoured rather than overridden.
        if options.browser_headless is None:
            options = replace(options, browser_headless=False)

        if self.family == "investigate":
            return investigate.investigate(self.target or "", repo, options, self.intent_text)
        if self.family == "verify":
            return verify.verify(self.target or "", repo, options, self.intent_text)
        if self.family == "report":
            return report.report(repo, options, self.intent_text)
        if self.family == "explain":
            return explain.explain(self.target or "", repo, options, self.intent_text)
        raise ValueError(f"unknown command family: {self.family}")

    def _run(self) -> None:
        """Drive the stream. Failure is reported, never papered over."""
        try:
            for ev in self._get_event_generator():
                with self._lock:
                    if self.cancelled:
                        return
                shown_before = self._lines_shown()
                self._consume(ev)
                self._pace(ev, shown_before)
                with self._lock:
                    if self.finished:
                        return
            # The stream ended without a terminal event. Say so, rather than
            # leaving the view spinning forever.
            with self._lock:
                reached_end = not self.finished and not self.cancelled
            if reached_end:
                self._log("the runtime closed the stream without reporting a result",
                          "wiz.warn")
                self._settle("incomplete")
        except Exception as exc:  # noqa: BLE001 — the real reason is the point
            message = str(exc) or exc.__class__.__name__
            self._log(f"failed · {message}", "wiz.err")
            with self._lock:
                self.status = "failed"
            self._settle("failed")

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------
    def _lines_shown(self) -> int:
        """How many lines the trace has, without holding the lock twice."""
        with self._lock:
            return len(self.activity)

    def _pace(self, ev: dict, shown_before: int) -> None:
        """Hold a narrated step on screen long enough to be read. Display only.

        Between events and never inside one: by the time this runs the node has
        already executed and its observation is already filed, so no ordering,
        outcome or upstream timing can depend on it. Pacing a stream is not the
        same as slowing a run down, and the difference is the whole reason this
        is allowed to exist at all.

        Only events that actually put a line on the trace are held. A run emits
        far more events than it shows — context packets, claim admissions, the
        browser plane's own narration — and paying the delay for each of them
        would multiply the run's length by the ratio of emitted to shown while
        changing nothing a viewer can see.

        Browser steps are held longer, because they are the ones with something
        to look at: the page pane beside the trace repaints on those events, and
        the reader is being given the time to watch a control change state. A
        file read has nothing to watch beyond its own line.

        `cancelled` is checked again between the two halves so a held step never
        becomes a held-up quit.
        """
        if self.pace <= 0:
            return
        if self._lines_shown() <= shown_before:
            return
        held = self.pace * (2.0 if str(ev.get("event_type", "")).startswith("browser.") else 1.0)
        deadline = time.monotonic() + held
        while (remaining := deadline - time.monotonic()) > 0:
            with self._lock:
                if self.cancelled:
                    return
            time.sleep(min(remaining, 0.05))

    def _log(self, text: str, style: str, kind: str = "step", role: str = "") -> None:
        with self._lock:
            self.activity.append(LogLine(text, style, kind, role))
            self.now = text
        self.on_change()

    def _settle(self, status: str) -> None:
        """Mark the run over, once."""
        with self._lock:
            self.status = status
            self.finished = True
            self.running = False
        self.on_change()

    def _consume(self, ev: dict) -> None:
        ev_type = ev.get("event_type", "")
        payload = ev.get("payload") or {}

        # Every event carries the Runtime's id for the run, so the first one
        # seen is recorded here — `cancel()` addresses the cancel endpoint by
        # that id, and an investigation with no id has nothing upstream to stop.
        # The API puts it on the event and inside its payload; read either.
        if not self.investigation_id:
            found = ev.get("investigation_id") or payload.get("investigation_id")
            if found:
                with self._lock:
                    self.investigation_id = str(found)

        if ev_type == "engine_unavailable":
            # The Runtime's own words — an HTTP refusal's `detail`, or the
            # connection error. This is the whole message; do not summarise it.
            reason = ev.get("error") or "the runtime did not answer"
            self._log(f"the runtime is unavailable · {reason}", "wiz.err",
                      role="runtime")
            with self._lock:
                self.status = "engine_unavailable"
            self._settle("engine_unavailable")
            return

        if ev_type == "done":
            with self._lock:
                self.status = ev.get("status", "completed")
                self.report_markdown = ev.get("report_markdown", "") or ""
                self.report_path = ev.get("report_path") or ""
            verdict = {
                "completed": "the investigation completed",
                "cancelled": "the investigation was cancelled",
                # Not the same claim as "completed", and the difference is the
                # whole point of the state: the run stopped, the goals did not
                # all close. Reading out the Runtime's own last_event adds why
                # (which goals stayed open, or that the budget ran out) instead
                # of leaving the reader to guess from a bare state name.
                "incomplete": "the investigation ended incomplete",
            }.get(self.status, f"the investigation ended · {self.status}")
            if self.status != "completed":
                reason = str((ev.get("stats") or {}).get("last_event") or "").strip()
                if reason:
                    verdict = f"{verdict} · {reason}"
            self._log(verdict, "wiz.ok" if self.status == "completed" else "wiz.warn",
                      role="runtime")
            self._settle(self.status)
            return

        # A verifier assessment can carry the Runtime's own next steps.
        if ev_type == "agent.assessed":
            recommended = payload.get("recommended_additional_investigations") or []
            with self._lock:
                self.nexts = [str(r) for r in recommended]

        # The page, taken before the line below is narrated and possibly dropped.
        # This is state a pane reads, not a log entry: a browser step whose
        # narration line got folded as a repeat is still the newest reading of
        # that page there is, and a live view that froze whenever the trace
        # decided a line was not news would freeze exactly when the page had
        # stopped changing — the moment its reader most wants to be sure it is
        # still being looked at.
        if ev_type.startswith("browser."):
            self._absorb_browser(ev_type, payload)

        line, style = _narrate(ev_type, payload)
        if line:
            if ev_type == "context_supplied":
                line = self._context_news(line, payload)
                if line is None:
                    return
            if self._is_echo(ev_type, payload, line):
                return
            if self._is_repeat_claim(ev_type, payload):
                return
            self._log(line, style, _KIND.get(ev_type, "step"),
                      _role(ev_type, payload))
            if ev_type == "agent.decided":
                with self._lock:
                    self._last_decision = line

    def _absorb_browser(self, ev_type: str, payload: dict) -> None:
        """Keep the newest page, and the last thing the run did to it.

        Both readings arrive on the same event and are kept apart on purpose.
        `page` is *where the browser is* — the url, the title, and every control
        it offers — and it is replaced outright, because it is a picture of one
        moment. `last_act` is *what the run just did there*, and it is the thing
        a viewer is actually looking for: the page lists every control, and a
        reader watching an app being driven wants to know which one was just
        touched and whether anything happened.

        The act is not folded into the page's controls even though it points at
        one of them. A control is what the page has; an act is what the run did,
        and the two have different lifetimes — the act outlives the control it
        names the moment a click navigates away, and a viewer is owed that fact
        rather than a marker silently vanishing. The pane matches them at render
        time and simply finds nothing to point at, which is the truth.
        """
        act = None
        if ev_type == "browser.acted":
            act = {
                "tool": payload.get("tool"),
                "selector": payload.get("selector"),
                "name": payload.get("selector_name"),
                "effect": payload.get("effect"),
                "value": payload.get("value"),
            }
        page = payload.get("page")
        with self._lock:
            if isinstance(page, dict):
                self.page = page
            if act is not None:
                self.last_act = act

    def _is_repeat_claim(self, ev_type: str, payload: dict) -> bool:
        """A claim the trace has already shown, with the same value it had then.

        Every browser step re-reads the page, so the run files `current_url` and
        `page_title` again after each one and a five-step interaction printed
        eight identical `WEB → current_url` lines. On a pane that shows a
        screenful, those repeats are what the lines carrying news are competing
        with: the user watching a sign-in go in reads eight rows saying the URL
        did not change and one saying the credentials landed.

        A claim that comes back with a DIFFERENT value is not a repeat and is
        never folded — that is the whole event. `current_url` changing from
        `/login` to `/tasks` is how the trace shows the sign-in worked, and
        folding it would be hiding the news to tidy up the noise.

        Only the trace is thinned. Every admission is still in the kernel's
        event history and in the report's Evidence Index, so nothing is lost —
        the same trade `_context_news` makes for the context packets.
        """
        if ev_type != "claim.admitted":
            return False
        # A payload with no `value` at all cannot distinguish a repeat from a
        # change, so it is never folded. The kernel has carried the value since
        # the fold was added, and a viewer talking to one that does not is not
        # entitled to guess: folding a changed URL would hide the one line that
        # says the page moved.
        if "value" not in payload:
            return False
        mark = (payload.get("claim_type"), payload.get("key"), _hashable(payload.get("value")))
        with self._lock:
            if mark in self._claims_seen:
                return True
            self._claims_seen.add(mark)
        return False

    def _is_echo(self, ev_type: str, payload: dict, line: str) -> bool:
        """A successful step finishing, saying what the step already said.

        `agent.decided` logs "→ read_file · client/package.json" and the
        `node.completed` that follows logs "✓ read_file · client/package.json":
        the same tool and the same subject, twice, one line apart, on every
        step of every run. The second says only that nothing went wrong, which
        a reader can already see in the absence of anything red — and on a pane
        this narrow, doubling the trace costs the lines that carry news.

        A step that FAILED is not an echo and is never suppressed: "! npm test ·
        …" is the one line in the pair that says something the decision did not.
        So is a completion with no decision above it, which is the only record
        that the step ran at all.
        """
        if ev_type != "node.completed" or not payload.get("ok", True):
            return False
        # The decision line is "→ toolsubject" and this one is "✓ toolsubject":
        # everything after the glyph has to match for this to be the same step.
        with self._lock:
            previous = self._last_decision
        if not previous:
            return False
        return previous[1:].strip() == line[1:].strip()

    def _context_news(self, line: str, payload: dict) -> str | None:
        """The audit line to log, or None when this packet repeats the last one.

        The audit is not lost either way — every supply is in the event stream,
        and the Context Engine's whole point is that one can reconstruct what an
        agent was given. This decides only what is worth a line on a screen that
        is already scrolling.

        A packet is news when its shape is new: the first one for an agent, one
        whose sections differ, one served from cache when the last was not. When
        it differs the line names what changed — `+queued_read_paths` is the part
        worth reading, and it is exactly the part a bare count hides.

        A refusal is never gated. The reader asked for a failure to be visible,
        and a refusal suppressed as a repeat is one they never learn about.
        """
        if payload.get("rejected"):
            return line
        agent = str(payload.get("agent_type") or "agent").lower()
        sections = tuple(payload.get("section_ids") or [])
        cached = bool(payload.get("from_cache"))
        with self._lock:
            previous = self._context_seen.get(agent)
            self._context_seen[agent] = (sections, cached)
        if previous == (sections, cached):
            return None
        if previous is None:
            return line
        was, _ = previous
        added = [s for s in sections if s not in was]
        dropped = [s for s in was if s not in sections]
        delta = ", ".join([f"+{s}" for s in added] + [f"-{s}" for s in dropped])
        return f"{line} · {delta}" if delta else line


# Which narration lines are the running commentary and which are raw evidence.
# Everything not named here is a step: a decision, a command, a goal closing, a
# verdict — the loop the reader is watching. Evidence admissions are the residue
# of those steps, one per observation, and they are the report's material.
#: What the run is doing, in the present tense, per tool.
#:
#: The kernel's registered tools are a closed set (`world/tools.py`
#: `_REGISTERED_TOOLS`) and this is a label for each of them — the same kind of
#: table as the kernel's own `_TOOL_TO_OBS_TYPE`, and no more of a claim than
#: that one. Every verb here is the plain description of what the tool does:
#: `read_file` reads a file and nothing else.
#:
#: A tool missing from this table is narrated under its own name, which is the
#: honest reading of a step this file has not been taught. Inventing a plausible
#: verb for a tool nobody has looked at is how a trace starts describing work
#: that did not happen.
_DOING: dict[str, str] = {
    "list_tree":        "listing",
    "read_file":        "reading",
    "search_files":     "searching for",
    "execute_command":  "running",
    "check_port":       "probing",
    "path_exists":      "checking",
    "start_process":    "starting",
    "read_process":     "reading",
    "kill_process":     "stopping",
    "list_processes":   "listing processes",
    "browser_navigate": "opening",
    "browser_snapshot": "reading the page",
    "browser_click":    "pressing",
    "browser_type":     "typing into",
    "browser_back":     "going back from",
    "browser_extract":  "extracting from the page",
}

_KIND: dict[str, str] = {"claim.admitted": "evidence"}


# Which part of the system each event came from. This is the runtime's own
# accounting read back out — every one of these names is either a field the
# event carries (`agent.decided`'s `source`, which the kernel sets to
# "explorer" or "node_plan" depending on which one actually proposed the
# action) or the component the kernel's own emit site belongs to. None of it is
# inferred, and an event nobody has classified shows no role rather than a
# guessed one.
_ROLE: dict[str, str] = {
    "investigation.started": "runtime",
    "goal.satisfied": "runtime",
    "node.completed": "runtime",
    "node.failed": "runtime",
    # The validator is the kernel refusing a request, not an agent making one.
    "tool.rejected": "runtime",
    "budget.low": "runtime",
    "budget.exhausted": "runtime",
    "investigation.incomplete": "runtime",
    "report.generated": "runtime",
    # The Context Engine's audit, assembled by the kernel before an agent is
    # asked anything — the agent did not choose what it was shown.
    "context_supplied": "context",
    "agent.consulted": "runtime",
    "agent.assessed": "verifier",
    "claim.admitted": "evidence",
    "planner.node_skipped": "planner",
    # The browser plane. The Explorer proposed these actions like any other, but
    # on a trace meant for someone watching a page being driven, "browser" is
    # the answer to what did that, and the decision line above already names the
    # Explorer as the one that asked for it.
    "browser.navigated": "browser",
    "browser.acted": "browser",
    "browser.extracted": "browser",
}


def _hashable(value: Any) -> Any:
    """A claim value in a form a set can hold.

    Claim values are mostly strings and numbers, but not all of them: a parsed
    manifest contributes lists (the requirement file's package names), and a set
    cannot hold a list. The repr is enough for the one question this answers —
    "is this the same value as before" — and a value that cannot be compared is
    better folded on its text than crashing the trace that is showing it.
    """
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    try:
        return repr(value)
    except Exception:  # noqa: BLE001 — a value that cannot be repr'd is not a crash
        return object()


def _role(ev_type: str, payload: dict) -> str:
    """Which component produced this event, for the flow pane's left column.

    `agent.decided` is the one that cannot be answered by event type alone, and
    it is the one that matters most: the kernel emits it for both paths through
    `_resolve_tool_action` and puts which one it was in `source`. The Explorer
    proposing a step from what the last read found, and the Planner's
    pre-planned step being carried out because the Explorer had nothing to say,
    look identical on the trace without this — so the whole difference between
    an investigation and a walk through a fixed script is invisible.
    """
    if ev_type == "agent.decided":
        source = str(payload.get("source") or "")
        if source == "explorer":
            return "explorer"
        if source == "node_plan":
            return "planner"
        return ""
    if ev_type == "node.started":
        # Same rule the browser.* events below are mapped by: on a trace meant
        # for someone watching a page being driven, "browser" is the answer to
        # what is doing that. A step the browser plane carries out belongs to
        # the browser plane, and every other tool belongs to the runtime that
        # invokes it.
        return "browser" if str(payload.get("tool") or "").startswith("browser_") else "runtime"
    return _ROLE.get(ev_type, "")


# ---------------------------------------------------------------------------
# Event -> narration. One entry per event the kernel actually emits; the fields
# read are the ones its own emit() calls set (control/loop.py).
# ---------------------------------------------------------------------------

def _seams(payload: dict) -> tuple[str, str]:
    """Name the implementation each port got, and flag one that is a mock.

    A Mock planner/explorer/verifier behaves like the real thing from the
    outside, so an unwired run is indistinguishable from a wired one unless
    this is read out. That is why the event exists — so the class names are the
    message, and the line turns red when any of them is a Mock.
    """
    impls = [str(payload.get(port) or "?") for port in ("planner", "explorer", "verifier")]
    joined = " · ".join(impls)
    if any(i.lower().startswith("mock") for i in impls):
        return f"not wired — running on {joined}", "wiz.err"
    return f"wired · {joined}", "wiz.dim"


def _subject(tool: str, params: dict) -> str:
    """What a decided action is actually aimed at, or "" if nothing names it.

    Naming only the tool made every step read as an identical "read_file": the
    trace said a file was read but never which one, and the same for a command.
    The parameter is the sanitised one the Runtime is about to use, so this is
    the real subject of the action, not a description of it.

    Empty rather than repeating the tool: a line reading "read_file · read_file"
    is noise, and a tool with no subject parameter (a browser snapshot, say) has
    nothing to add.

    Long paths are cut from the left, keeping the tail — "…/middleware/auth.js"
    still says which file it is, where "server/src/middleware/aut…" does not.
    """
    if not isinstance(params, dict):
        return ""
    # The parameter that names the subject, per tool (world/tools.py).
    for key in ("path", "command", "pattern", "url", "selector", "directory"):
        value = params.get(key)
        if isinstance(value, str) and value.strip():
            text = " ".join(value.split())
            if len(text) <= _SUBJECT_MAX:
                return text
            return "…" + text[-(_SUBJECT_MAX - 1):]
    if params.get("port") is not None:
        return f"port {params['port']}"
    return ""


def _narrate(ev_type: str, payload: dict) -> tuple[str, str]:
    """Map a runtime event to a flow-narration line + style."""
    if ev_type == "seams.resolved":
        return _seams(payload)

    if ev_type == "investigation.started":
        return "the runtime accepted the request", "wiz.flow"

    if ev_type == "agent.consulted":
        agent = str(payload.get("agent_type") or "agent").lower()
        who = "the Explorer" if "explor" in agent else "the Verifier" if "verif" in agent else agent
        reviewed = payload.get("claims_reviewed")
        detail = f" ({reviewed} claims)" if reviewed is not None else ""
        return f"→ consulting {who}{detail}", "wiz.flow"

    if ev_type == "context_supplied":
        # The Context Engine's audit line: what it handed an agent to work from.
        # The token total it carries is deliberately not shown — this screen is
        # where a fabricated token meter used to sit, and a guard forbids the
        # word. The section count says the same thing without reopening it.
        #
        # "context" is not repeated in the text: the pane's own column says
        # which component this is, and on a line this narrow the second mention
        # is a word spent to say nothing.
        who = str(payload.get("agent_type") or "an agent").lower()
        if payload.get("rejected"):
            return (f"✗ context refused · {payload.get('reason') or 'rejected'}"), "wiz.err"
        sections = payload.get("section_ids") or []
        suffix = " · cached" if payload.get("from_cache") else ""
        return f"→ {len(sections)} sections to {who}{suffix}", "wiz.flow"

    if ev_type == "agent.decided":
        tool = payload.get("tool") or "?"
        subject = _subject(tool, payload.get("params") or {})
        reason = " ".join((payload.get("reason") or "").split())
        # The rationale is a whole sentence ("Establish evidence toward goal:
        # investigate architecture") that repeats identically on every decision,
        # and the pane is narrow. Appended in full it wraps each line onto a
        # second row; cut to fit it dangles mid-sentence, which reads as broken.
        # So it is shown when it fits and left off when it does not — the
        # decision itself is the traceable fact here, and the whole rationale is
        # still in the event stream.
        #
        # The subject earns the space the source ("explorer" / "node_plan") used
        # to take: both are in the event, but on a narrow pane a line that says
        # which file was read beats one that says which seam proposed it.
        suffix = f" · {reason}" if 0 < len(reason) <= _REASON_MAX else ""
        head = f"→ {tool} · {subject}" if subject else f"→ {tool}"
        return f"{head}{suffix}", "wiz.flow"

    if ev_type == "agent.assessed":
        # The verdict is one of two literals (contracts/agent.py). Style by the
        # verdict and not by the mere fact that an assessment arrived: a green
        # check beside "needs_more_work" says the opposite of what the Verifier
        # said, and it is the kind of plausible-looking lie this view exists to
        # avoid.
        assessment = str(payload.get("assessment") or "")
        weak = payload.get("weak_claims") or []
        extra = f" · {len(weak)} weak" if weak else ""
        # The Runtime asks for a last review once the goals are closed, and does
        # not act on it — the run is over either way. Narrated identically to the
        # mid-run consultations, that final "needs more work" read as the run
        # contradicting itself one line above "the investigation completed", when
        # the two are not in conflict: one is an opinion recorded at the end, the
        # other is what the goals actually closed on.
        closing = payload.get("escalated") is False
        # "verifier · …" under a column that already reads "verifier" spends a
        # third of a narrow line restating the column. What the last review has
        # that the mid-run ones do not is that it is the last one, so that is
        # the word kept.
        lead = "final · " if closing else ""
        if assessment == "overall_sufficient":
            return f"✓ {lead}overall sufficient{extra}", "wiz.ok"
        if assessment == "needs_more_work":
            tail = " · noted, not acted on" if closing else ""
            return f"! {lead}needs more work{extra}{tail}", "wiz.warn"
        # An assessment this file does not know about is shown as the Runtime
        # named it, with no verdict glyph attached.
        return f"{lead}{assessment or 'no assessment'}{extra}", "wiz.dim"

    if ev_type == "claim.admitted":
        # "found evidence · " used to lead this. The pane now says which of the
        # four kinds a line is in its own left column, so the prefix repeated
        # the column in words and pushed the one thing worth reading — which
        # claim was admitted — off the end of a narrow line.
        return (f"{payload.get('claim_type', '?')} → "
                f"{payload.get('key', '?')}"), "wiz.evidence"

    if ev_type == "planner.node_skipped":
        return (f"· planner step already queued · "
                f"{payload.get('type', 'node')} skipped"), "wiz.dim"

    if ev_type == "goal.satisfied":
        return f"★ goal satisfied · {payload.get('goal_name', '?')}", "wiz.ok"

    if ev_type == "node.failed":
        return (f"✗ node {payload.get('node_id', '?')} "
                f"({payload.get('reason', 'failed')})"), "wiz.err"

    if ev_type == "tool.rejected":
        # The subject matters more on a refusal than on a success: "read_file
        # rejected · duplicate" leaves the reader unable to tell which file the
        # Runtime refused to read twice, which is the whole content of the line.
        tool = payload.get("tool", "tool")
        subject = _subject(tool, payload.get("params") or {})
        head = f"✗ {tool} · {subject} rejected" if subject else f"✗ {tool} rejected"
        return f"{head} · {payload.get('reason', 'not allowed')}", "wiz.err"

    if ev_type == "budget.low":
        return (f"budget low · {payload.get('remaining', '?')} of "
                f"{payload.get('total', '?')} left"), "wiz.warn"

    if ev_type == "budget.exhausted":
        return (f"budget exhausted · used {payload.get('used', '?')} of "
                f"{payload.get('total', '?')}"), "wiz.warn"

    if ev_type == "investigation.incomplete":
        # The kernel emits this with the reason and the goals it could not
        # close, and nothing narrated it: the line read "· investigation.
        # incomplete", which is the event's own name and tells the reader
        # nothing they did not already know from the run having stopped. The
        # payload is the answer to the only question left — which goals stayed
        # open, and why the loop gave up on them.
        reason = payload.get("reason") or "the loop ended"
        open_goals = [str(g) for g in (payload.get("open_goals") or [])]
        tail = f" · still open: {', '.join(open_goals)}" if open_goals else ""
        return f"✗ ended incomplete · {reason}{tail}", "wiz.warn"

    if ev_type == "report.generated":
        # The path the kernel writes is inside the engine's own artifact
        # directory — `wizard-runtime-engine/.wizard/investigations/<id>/` —
        # and it is not the file the reader opens. The CLI saves its own copy
        # beside them in `output/` and the footer names that one, so echoing
        # the engine's path here put two different absolute paths on one screen
        # and left the reader to work out which of the two was the report. The
        # path is still in the event stream for anything reading it
        # programmatically; this line reports that the report exists.
        return "report written", "wiz.ok"

    if ev_type == "browser.navigated":
        title = payload.get("title") or ""
        return (f"◈ navigate · {payload.get('url', '?')} "
                f"[{payload.get('status', '?')}]" + (f" · {title}" if title else "")), "wiz.flow"

    if ev_type == "browser.acted":
        # What was done to the control, and what the control did back.
        #
        # The kernel has put `effect` and `value` on this event since the browser
        # learned to operate a page, and this line read neither: it named the
        # tool and the selector and stopped, so the trace reported that a button
        # had been pressed without ever saying whether anything happened. That
        # is the whole finding of an interaction — the one thing a run that
        # drives an application learns and a run that only reads it cannot — and
        # it was the one thing the pane left out.
        tool = str(payload.get("tool") or "?")
        selector = payload.get("selector") or payload.get("url") or ""
        if tool == "browser_type" and payload.get("value") is not None:
            # The value is the field's own reading after the keystroke, not the
            # text that was sent, so a controlled input that refuses what it is
            # given shows as what actually landed.
            head = f"typed {selector} = {payload['value']!r}"
        elif tool == "browser_click":
            head = f"pressed {selector}"
        elif selector:
            head = f"{tool} · {selector}"
        else:
            head = tool
        effect = payload.get("effect")
        # "page unchanged" is not styled as a failure, because it is not one to
        # this pane: whether an inert control is a defect is a judgement about
        # the application, and the extractor files the same reading as a finding
        # rather than a contradiction for exactly this reason. The words say
        # what was seen; the reader decides what it means.
        tail = f" · page {effect}" if effect else ""
        return f"◈ {head}{tail}", "wiz.flow"

    if ev_type == "browser.extracted":
        # The two extraction tools measure different things: `browser_snapshot`
        # walks the accessibility tree and reports `node_count`, and
        # `browser_extract` reads the page's text and has no tree to count. The
        # event carries whichever the tool actually produced, so the line shows
        # the counts that are there and stays silent about the one that is not
        # — a placeholder would be a number the tool never measured.
        def _count(value, noun: str) -> str | None:
            if value is None:
                return None
            return f"{value} {noun}" + ("" if value == 1 else "s")

        parts = [p for p in (_count(payload.get("node_count"), "node"),
                             _count(payload.get("link_count"), "link")) if p]
        detail = " · " + ", ".join(parts) if parts else ""
        return f"◈ extracted{detail}", "wiz.evidence"

    if ev_type == "node.started":
        # The step happening, said while it is happening.
        #
        # Every other line on this pane is retrospective — the decision before
        # it and the result after it — so a run read as a plan being accepted
        # followed by a column of answers, with the work itself nowhere between
        # them. Paired with the pacing in `_run`, this is the line that makes a
        # run look like something being done rather than something being
        # reported.
        #
        # A phrase rather than the tool name, because the tool name is already
        # on the two lines either side of this one and a third reading of it
        # says nothing new. The phrase is a label for the tool, not a claim
        # about it — the same kind of table as `_TOOL_TO_OBS_TYPE` in the
        # kernel — and a tool this file has not been taught falls back to its
        # own name, which is the honest reading of an unfamiliar step.
        tool = str(payload.get("tool") or "")
        subject = _subject(tool, payload.get("params") or {})
        doing = _DOING.get(tool, tool or "working")
        return (f"▶ {doing} {subject}" if subject else f"▶ {doing}", "wiz.accent")

    if ev_type == "node.completed":
        # The subject, not the node id: "node n7" tells a reader nothing about
        # what the investigation just did, and the id is already how the Runtime
        # refers to it internally. The tool and what it was aimed at is the step
        # the user is watching for.
        tool = payload.get("tool", "step")
        subject = _subject(tool, payload.get("params") or {})
        # A tool can succeed at the transport level and still report failure —
        # a command that ran and exited non-zero is the ordinary case — so the
        # line has to distinguish "the step happened" from "the step worked".
        ok = payload.get("ok", True)
        mark, style = ("✓", "wiz.ok") if ok else ("!", "wiz.warn")
        tail = f"{tool} · {subject}" if subject else tool
        return f"{mark} {tail}", style

    if ev_type:
        # Unknown but real: name it rather than hide it. A new kernel event
        # should show up here as itself, not as an invented step.
        return f"· {ev_type}", "wiz.dim"

    return "", "wiz.flow"
