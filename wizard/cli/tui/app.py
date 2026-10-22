"""The Wizard TUI application — a single prompt_toolkit full-screen app.

prompt_toolkit owns the event loop, the alternate screen, and all keyboard
input; that single ownership is what keeps the screen from breaking and lets an
input box stay live *during* an investigation. Rich only builds the content of
the two boxes (see widgets.py), which we rasterize to ANSI each frame.

The layout is three stacked pieces: the identity panel on top, one bordered
command box holding whatever the current screen is, and the real input box
underneath. The panel is constant, so its Window has a fixed height and is
rendered once; the command box is the Window that scrolls — wheel, arrows,
PgUp/PgDn, Home/End — with a scrollbar in its margin. That split is the reason
scrolling the flow does not drag the wizard off the top of the screen.

State machine:  MENU → INTENT → WORKING → RESULT
A ~0.08s refresh drives the ember animation; a background worker (session.py)
streams real runtime events and calls `app.invalidate()` to redraw. A finished
run crosses to RESULT on its own last event rather than waiting to be asked.
"""

from __future__ import annotations

import os
import threading
import time
from uuid import uuid4

from prompt_toolkit.application import Application
from prompt_toolkit.data_structures import Point
from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import (
    ConditionalContainer,
    Float,
    FloatContainer,
    HSplit,
    Window,
)
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.margins import ScrollbarMargin
from prompt_toolkit.mouse_events import MouseEventType
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import Frame, TextArea

from wizard.cli.parser.command_parser import BTW_COMMANDS, COMMAND_TARGETS, SLASH_COMMANDS
from wizard.cli.parser.frontend import Frontend, suggestion_for
from wizard.cli.tui import history
from wizard.cli.tui.session import TuiSession
from wizard.cli.tui.slash_menu import SlashCompleter, SlashMenu
from wizard.cli.tui.widgets import (
    command_box,
    intent_content,
    menu_content,
    page_content,
    render_to_ansi,
    result_content,
    top_panel,
    top_panel_height,
    working_content,
)

# Screen states. There is no splash: the identity panel is the welcome, and it
# is on screen in every state, so a separate first screen would be one the user
# has to dismiss before reaching the thing they came for.
MENU, INTENT, WORKING, RESULT = "menu", "intent", "working", "result"

# Command families offered in the menu, sourced live from the canonical
# registry (no duplicate list). Order is stable/insertion order.
FAMILIES = list(COMMAND_TARGETS.keys())



class _FixedControl(FormattedTextControl):
    """A control that refuses to be scrolled.

    prompt_toolkit scrolls a Window on its own whenever the wheel turns over it
    and the content is taller than the viewport — see `Window._mouse_handler`.
    The panel above the command box is not a thing anyone means to scroll, so
    without this a wheel over it either does nothing visible or shifts the
    identity panel up out of its own border.

    Returning `None` rather than `NotImplemented` is the whole trick: the
    Window's wrapper treats `NotImplemented` as "I didn't want this, you take
    it" and scrolls, whereas `None` means "handled, nothing to do".
    """

    def mouse_handler(self, mouse_event):
        if mouse_event.event_type in (MouseEventType.SCROLL_UP,
                                      MouseEventType.SCROLL_DOWN):
            return None
        return super().mouse_handler(mouse_event)


class _CommandControl(FormattedTextControl):
    """Give the existing command menu real mouse focus and row selection."""

    def __init__(self, *args, menu_mouse, **kwargs):
        super().__init__(*args, **kwargs)
        self.menu_mouse = menu_mouse

    def mouse_handler(self, mouse_event):
        if self.menu_mouse(mouse_event):
            return None
        return super().mouse_handler(mouse_event)


class WizardTUI:
    """Owns all mutable UI state and wires prompt_toolkit together."""

    def __init__(self, repo_path: str | None = None) -> None:
        self.modern_ui = os.environ.get("WIZARD_UI") == "modern"
        self.state = MENU
        self._start = time.monotonic()

        # Menu selection state
        self.menu_level = "family"          # "family" | "target"
        self.selected = 0
        self.family: str | None = None
        self.target: str | None = None
        # The text last typed into the box, kept because the history records
        # what the user asked for and the box is cleared before the run starts.
        self.raw_intent: str = ""
        self.show_report = False


        # The directory the run investigates: the one named on the command line
        # (`wizard C:/somewhere`), or where the user launched from.
        self.repo_path = (
            os.path.abspath(os.path.expanduser(repo_path)) if repo_path
            else os.getcwd()
        )

        self.session: TuiSession | None = None
        self.side_chat = None
        self.show_btw = False
        self._btw_session_id = str(uuid4())
        self._chat_drafts = {False: "", True: ""}
        self._chat_scroll = {False: 0, True: 0}

        # The web client this repository serves, and the line that tells the
        # user how to get a browser phase for it. Found when the intent screen
        # opens — a human moment, not a frame — because finding it costs a
        # package.json walk and a TCP connect, and this screen redraws twelve
        # times a second.
        self.frontend: Frontend | None = None
        self.frontend_hint: str = ""

        # Frames for the screens that do not move. See _render_body.
        self._static_frames: dict[tuple, object] = {}
        # Where the tail was on the last frame, for the follow-the-run rule.
        # See _follow_tail.
        self._pinned_top = 0

        # Whether the right pane is showing the flow or the page the browser is
        # on. The two are the same pane rather than two panes because at the
        # width the wizard art leaves — around forty columns on a normal
        # terminal — a third column would be too narrow to read a control's
        # name in, and both views are things a reader looks at one at a time.
        self.show_page = False
        # Whether the pane has already turned itself to the page once. Back to
        # false with the run, for the same reason `show_page` is: the next
        # investigation's page has not arrived yet. See _follow_page.
        self._page_followed = False
        self._usage_report = None
        self._status_input = False
        self._status_request = None
        self._exiting = False
        self._input_notice = ""
        self._account_login = None
        self._account_name = "default user"
        self._account_id = None
        self._session_account_id = None
        self._account_revision = 0
        self._account_state_lock = threading.RLock()
        self._auth_operation = object()
        self._account_logout_running = False

        # One input buffer remains editable while the worker drives the run.
        self.input = TextArea(
            prompt="› ",
            multiline=False,
            wrap_lines=False,
            accept_handler=self._on_accept,
            height=1,
            read_only=Condition(lambda: False),
            completer=SlashCompleter(dict(SLASH_COMMANDS)),
            complete_while_typing=False,  # The inline menu owns highlighting, not buffer preview edits.
            focus_on_click=True,
        )
        self.input_frame = Frame(self.input, title="Intent / command", style="class:inputbox")
        self.composer = (HSplit([
            Window(height=1, char="─", style="class:composer-line"),
            self.input,
            Window(height=1, char="─", style="class:composer-line"),
        ]) if self.modern_ui else self.input_frame)
        self.slash_menu = SlashMenu(self.input.buffer, self.input.completer,
            focused=lambda: hasattr(self, "app") and self.app.layout.has_focus(self.input),
            size=self._geometry)

        # --- top window: the identity panel, fixed height, never scrolls ---
        # A fixed height — counted off the art and the terminal — is what makes
        # the panel a header rather than the first screen of a scrolling
        # document: the box below it is then the only thing that moves, and the
        # wizard stays where it was put. The height depends on the terminal,
        # because the art is drawn at the densest packing that fits and a short
        # terminal gets the smaller, denser one.
        self.top_window = Window(
            content=_FixedControl(self._render_top),
            height=lambda: 3 if self.modern_ui else top_panel_height(self._geometry()[1], self._geometry()[0]),
            wrap_lines=False,
            always_hide_cursor=True,
        )

        # --- body window: the command box, scrollable ---
        # `focusable`: this window takes focus in every state except INTENT, so
        # the scroll keys land here rather than in the text box.
        self.body = Window(
            content=_CommandControl(
                self._render_body,
                menu_mouse=self._menu_mouse,
                focusable=True,
                # Without this, scrolling does not stick. A Window's `_scroll`
                # keeps the *cursor* visible, and this control's cursor sits at
                # line 0, so every render clamps the offset straight back to the
                # top — the pane would take a scroll and silently undo it.
                # Reporting the cursor at the scrolled line makes "keep the
                # cursor visible" mean "keep this line visible", which is the
                # invariant we actually want.
                get_cursor_position=lambda: Point(x=0, y=self._cursor_line()),
            ),
            wrap_lines=False,
            right_margins=[ScrollbarMargin(display_arrows=True)],
            # The pane has no text cursor; a block parked on its first line
            # would just look like a rendering fault.
            always_hide_cursor=True,
        )
        self.right_window = self.body
        self.scroll = 0
        # The line count of the box as last rendered. Written by `_render_body`
        # and read by `_cursor_line` on the very next call, which is what makes
        # the scroll offset safe. See `_cursor_line`.
        self._body_lines = 1
        self.usage_window = Window(
            content=FormattedTextControl(self._render_usage), height=1,
            wrap_lines=False, always_hide_cursor=True, style="class:usage",
        )

        root = HSplit(
            [
                self.top_window,
                self.body,
                ConditionalContainer(Window(content=FormattedTextControl(self._report_actions), height=1, always_hide_cursor=True),
                    filter=Condition(lambda: self.session is not None and self.state in (WORKING, RESULT))),
                ConditionalContainer(self.usage_window, filter=Condition(
                    lambda: self.session is not None and self.state in (WORKING, RESULT))),
                self.composer,
                ConditionalContainer(
                    Window(content=FormattedTextControl(lambda: [("class:usage", self._input_notice)]),
                           height=self._notice_height, wrap_lines=True, always_hide_cursor=True),
                    filter=Condition(lambda: bool(self._input_notice))),
            ]
        )


        self.composer_overlay = FloatContainer(content=root, floats=[
            Float(content=self.slash_menu.container, left=1, right=1, ycursor=True,
                  attach_to_window=self.input.window),
        ])
        if self.modern_ui:
            def render_companion():
                from wizard.cli.tui.modern import companion
                return render_to_ansi(companion(), 40)
            self.composer_overlay.floats.append(Float(right=2, bottom=4, width=40, height=27,
                content=ConditionalContainer(Window(content=FormattedTextControl(render_companion),
                    always_hide_cursor=True), filter=Condition(lambda:
                        self.state == MENU and not self.show_btw and not self._usage_report
                        and not self._input_notice and self._geometry()[0] >= 100
                        and self._geometry()[1] >= 40))))
        self.app: Application = Application(
            layout=Layout(self.composer_overlay, focused_element=self.input if self.modern_ui else self.right_window),
            key_bindings=self._bindings(),
            style=Style.from_dict(
                {
                    "": "bg:#08080A #F3F1EC" if self.modern_ui else "",
                    "composer-line": "#9B7EDE",
                    "inputbox": "#c084fc",           # visible violet frame border
                    "inputbox frame.border": "#c084fc",
                    "usage": "#7E7C88" if self.modern_ui else "#b8b1c5",
                    "slash-menu": "bg:#211a2e #b8b1c5",
                    "slash-menu.selected": "bg:#24202F #F3F1EC bold" if self.modern_ui else "bg:#5b2d7a #ffffff bold",
                }
            ),
            full_screen=True,
            # Mouse support ON, deliberately. The failure the user hit with it
            # OFF is the decisive evidence: scrolling the wheel made the terminal
            # fall back to emitting arrow-key sequences (`^[[A`/`^[[B`), which
            # leaked onto the screen as literal text. With mouse reporting ON the
            # terminal sends SGR mouse events instead, which prompt_toolkit
            # consumes (and maps wheel-up/down to scrolling) rather than letting
            # them fall through as keys. Disabling the wheel is not the fix — the
            # terminal still has to report the wheel somehow, and the arrow-key
            # fallback is the one shape that leaks. External text (page DOM,
            # control labels) is still scrubbed by sanitize_terminal(); this
            # setting governs the live INPUT the terminal sends back.
            mouse_support=True,
            refresh_interval=None if self.modern_ui else 0.08,
        )

    # ------------------------------------------------------------------
    # Timing / geometry
    # ------------------------------------------------------------------
    def _t(self) -> float:
        return time.monotonic() - self._start

    def _geometry(self) -> tuple[int, int]:
        """(columns, rows) of the terminal, with a sane fallback off-screen."""
        try:
            size = self.app.output.get_size()
            return size.columns, size.rows
        except Exception:
            return 100, 30

    # ------------------------------------------------------------------
    # Content rendering (per frame)
    # ------------------------------------------------------------------
    def _render_top(self):
        """Cache the identity panel until the account or terminal size changes."""
        width, rows = self._geometry()
        identity = (width, rows, self._account_name)
        cached = self._static_frames.get("top")
        if cached is None or self._static_frames.get("top_identity") != identity:
            if self.modern_ui:
                from wizard.cli.tui.modern import header
                content = header(self.repo_path, self._account_name)
            else:
                content = top_panel(self.repo_path, rows, width, self._account_name)
            cached = render_to_ansi(
                content, width
            )
            self._static_frames["top"] = cached
            self._static_frames["top_identity"] = identity
        return cached

    def _surface(self, content):
        if self.modern_ui:
            from wizard.cli.tui.modern import surface
            return surface(content)
        return command_box(content)

    def _render_body(self):
        """The command box — the whole current screen, inside one border."""
        width, _ = self._geometry()
        t = self._t()
        if self.show_btw and self._usage_report is None:
            from rich.text import Text

            from wizard.cli.tui.session import sanitize_terminal
            snap = self.side_chat.snapshot()
            content = Text("/btw · " + snap["id"] + "\n\n")
            for message in snap["messages"]:
                content.append("You\n" if message["role"] == "user" else "Wizard\n", style="bold")
                content.append(sanitize_terminal(message["content"]) + "\n\n")
            if snap["pending"]:
                content.append("Thinking… You can navigate while the response finishes.\n")
            if snap["error"]:
                content.append(snap["error"] + "\n", style="red")
            content.append("\nNavigate to main chat: /btw main · Alt+B\n"
                           "Copy answer: /btw copy · Copy transcript: /btw copy all\n"
                           "New conversation: /btw new · /exit quits Wizard")
            rendered = render_to_ansi(self._surface(content), width)
            self._body_lines = rendered.value.count("\n") + 1
            return rendered
        if self._usage_report is not None:
            from rich.text import Text
            rendered = render_to_ansi(self._surface(Text(self._usage_report)), width)
            self._body_lines = rendered.value.count("\n") + 1
            return rendered

        # Everything but WORKING and RESULT is static — nothing on those screens
        # is a function of time — so their frame is cached against everything
        # that can change it. Without this the box is re-rasterized on every
        # refresh tick. WORKING and RESULT carry the ember and the elapsed clock,
        # so they always re-render.
        static = self.state in (MENU, INTENT)
        key = ("body", self.state, width, self.menu_level, self.selected,
               self.family, self.target, self.repo_path, self.frontend_hint, bool(self.side_chat))
        if static:
            cached = self._static_frames.get(key)
            if cached is not None:
                # A cached frame still has to declare its height. Returning it
                # without doing so leaves `_body_lines` describing whatever was
                # on screen before — so coming back from a long trace to this
                # short menu is the same stale-height crash the record exists to
                # prevent, just reached through the cache instead of a re-render.
                self._body_lines = cached.value.count("\n") + 1
                return cached

        if self.state == MENU:
            options = self._current_options()
            if self.modern_ui:
                from wizard.cli.tui.modern import welcome
                content = welcome(self.menu_level, options, self.selected, self.family, self.repo_path)
            else:
                content = menu_content(self.menu_level, options, self.selected, self.family)

        elif self.state == INTENT:
            if self.modern_ui:
                from wizard.cli.tui.modern import intent
                content = intent(self.family, self.target, self.repo_path)
            else:
                content = intent_content(self.family, self.target, self.repo_path,
                                         self.frontend_hint, self.frontend is not None)

        elif self.state == WORKING:
            s = self.session
            # Before the box is built rather than after, so the first frame
            # that could carry the page is the frame that carries it.
            self._follow_page()
            snap = s.snapshot() if s else {}
            snap["usage_in_footer"] = True
            if self.show_page:
                content = page_content(snap, t, width)
            else:
                content = working_content(
                    self.family or "investigate",
                    snap,
                    s.snapshot_activity() if s else [],
                    t,
                )

        elif self.state == RESULT:
            s = self.session
            snap = s.snapshot() if s else {}
            diagram = getattr(self, "_diagram", None)
            if diagram and diagram[0] is s:
                snap["report_markdown"] = diagram[2] + "\n\n" + snap.get("report_markdown", "")
            snap["usage_in_footer"] = True
            if self.show_page:
                content = page_content(snap, t, width)
            else:
                content = result_content(self.family or "investigate", snap, t)

        else:
            content = menu_content("family", FAMILIES, self.selected, self.family)

        if self.show_report and self.session and self.state in (WORKING, RESULT):
            from rich.markdown import Markdown
            report_text = self.session.snapshot().get("report_markdown") or "Report is waiting for discovery."
            report_key = (report_text, width)
            previous = getattr(self, "_runbook_frame", None)
            if previous and previous[0] == report_key and not self.side_chat:
                self._body_lines = previous[1].value.count("\n") + 1
                return previous[1]
            content = Markdown(report_text)

        if self.side_chat:
            from rich.console import Group
            from rich.text import Text
            content = Group(content, Text("\nReturn to your conversation: /btw return · Alt+B"))
        rendered = render_to_ansi(self._surface(content), width)
        if self.show_report and self.session and self.state in (WORKING, RESULT) and not self.side_chat:
            self._runbook_frame = (report_key, rendered)
        if self.state == WORKING and not self.show_report:
            self._follow_tail()
        # Recorded here, not read off `render_info`, because this is the content
        # the renderer is about to ask for a cursor line *in*. `render_info` is
        # the previous frame's measurement, so a frame whose content is shorter
        # than the last one reports a height that no longer exists — which is
        # precisely the case that raises. See `_cursor_line`.
        self._body_lines = rendered.value.count("\n") + 1
        if static:
            if len(self._static_frames) > 64:   # a resize storm must not grow it
                self._static_frames.clear()
                self._render_top()
            self._static_frames[key] = rendered
        return rendered

    def _report_action(self, action):
        if action == "view":
            self.show_report = not self.show_report
            self.show_page = False
            self.scroll = 0
        elif action == "open" and self.session:
            from pathlib import Path
            import webbrowser
            run_id = self.session.snapshot().get("investigation_id")
            if run_id:
                path = Path(self.repo_path or ".") / "output" / (run_id + ".runbook.html")
                if path.is_file():
                    webbrowser.open(path.resolve().as_uri())
        elif action == "copy" and self.session:
            from wizard.cli.tui.clipboard import ClipboardError, write_text
            steps = (self.session.snapshot().get("runbook") or {}).get("steps", [])
            commands = [str((step.get("parameters") or {}).get("command", "")) for step in steps
                        if step.get("tool") in {"start_process", "execute_command"}]
            try:
                if commands:
                    write_text("\n".join(commands))
                    self._input_notice = "Copied recorded commands. Review working directories and redacted values before running."
                else:
                    self._input_notice = "No startup command has been recorded."
            except ClipboardError as exc:
                self._input_notice = str(exc)
        elif action == "rerun" and self.state == RESULT:
            # Normal submission: fresh run, validation, sessions, and provider budget.
            self._begin_work(self.raw_intent)
        self.app.invalidate()

    def _report_actions(self):
        from prompt_toolkit.mouse_events import MouseEventType
        def handler(action):
            def click(event):
                if event.event_type == MouseEventType.MOUSE_UP:
                    self._report_action(action)
            return click
        items = [("class:usage", " [F3 Live report] ", handler("view")),
                 ("class:usage", " [F6 Copy commands] ", handler("copy"))]
        if self.state == RESULT:
            items += [("class:usage", " [F4 Open report/map] ", handler("open")),
                      ("class:usage", " [F5 Rerun (uses credits)] ", handler("rerun"))]
        return items

    def _render_usage(self):
        """Pinned outside the scrollable flow, including page/status views."""
        from wizard.cli.display.usage import counter
        snap = self.session.snapshot() if self.session else {}
        if self.session and not self._owns_usage_session():
            return [("class:usage", "Previous account run. /status shows current account usage.")]
        elapsed = (snap.get("ended_at") or time.monotonic()) - snap.get("started_at", time.monotonic())
        return [("class:usage", counter(snap.get("usage"), elapsed, compact=True))]

    def _owns_usage_session(self):
        if not self.session:
            return False
        profile = (self.session.snapshot().get("usage") or {}).get("profile_id")
        if isinstance(profile, str) and profile.startswith("account:"):
            return profile == "account:" + str(self._account_id)
        if profile and self._account_id:
            return False
        return self._session_account_id == self._account_id


    # ------------------------------------------------------------------
    # Scrolling
    # ------------------------------------------------------------------
    @property
    def scroll(self) -> int:
        """The right pane's offset. The Window owns it; this is a view of it.

        prompt_toolkit's own wheel handling writes `vertical_scroll` directly on
        the Window, so keeping a second copy here would drift the moment anyone
        used the wheel — and the next arrow key would snap the view back to
        wherever the stale copy said it was.
        """
        return self.right_window.vertical_scroll

    @scroll.setter
    def scroll(self, value: int) -> None:
        self.right_window.vertical_scroll = value

    def _scroll_bounds(self) -> tuple[int, int]:
        info = self.right_window.render_info
        if info is None:
            return 0, 10
        page = max(1, info.window_height - 1)
        return max(0, info.content_height - info.window_height), page

    def _cursor_line(self) -> int:
        """The scroll offset, held inside the content that is actually there.

        This control reports the scroll offset as its cursor position so that
        prompt_toolkit's "keep the cursor visible" *is* "keep the scrolled line
        visible". The catch is that the offset is a number this class remembers
        while the content is a number that changes: a run ends and the box
        becomes a report, the reader flips between the flow and the page pane, a
        new run starts with an empty trace. Any of those leaves the offset
        pointing past the last line, and prompt_toolkit reads the cursor line
        straight out of its own content — `fragment_lines[i]` — so an offset one
        past the end is an IndexError raised inside the renderer, which surfaces
        as an unhandled exception in the event loop.

        The ceiling has to be the line count of the frame being drawn, which is
        why `_render_body` records it as it produces the text. Clamping against
        `render_info` instead does not work and was the first attempt at this:
        that is the *previous* frame's measurement, so on the one frame that
        matters — content shorter than it was last time — it reports a height
        that no longer exists and lets the bad offset straight through.
        `render_info` is still consulted, but only as a second, lower ceiling; a
        stale-small value under-clamps by a line, which costs nothing, where a
        stale-large one crashes.
        """
        info = self.right_window.render_info
        last = max(0, info.content_height - 1) if info is not None else 0
        return max(0, min(self.scroll, self._body_lines - 1, last))

    def _follow_tail(self) -> None:
        """Keep a live run showing its newest line.

        Only a run follows: a report should open at its beginning, not at its
        end. "Was at the bottom on the last frame" is the user's own signal, so
        an explicit scroll away turns following off without a flag that the
        wheel — which prompt_toolkit handles itself, behind our back — would
        bypass and then fight.
        """
        top, _ = self._scroll_bounds()
        was_at_bottom = self.scroll >= self._pinned_top
        self._pinned_top = top
        if was_at_bottom:
            self.scroll = top

    def _scroll_by(self, delta: int) -> None:
        top, _ = self._scroll_bounds()
        # Clamped here rather than left to prompt_toolkit, which stops at
        # `content_height - 1` and would park the view on the last line.
        self.scroll = max(0, min(self.scroll + delta, top))

    def _reset_scroll(self) -> None:
        self.scroll = 0
        self._pinned_top = 0

    def _has_page(self) -> bool:
        """Whether the browser has shown us a page yet. Read off the session."""
        s = self.session
        if s is None:
            return False
        return isinstance(s.snapshot().get("page"), dict)

    def _follow_page(self) -> None:
        """Turn to the page the first time the browser reaches one.

        `b` is how a reader goes back to the flow once they have seen the page;
        it is not how they should have to find out the page exists. A run that
        drives a real browser and shows nothing about the application it was
        driving has hidden the half of the work a terminal cannot otherwise
        show — and the reader's only clue would be a one-line key hint at the
        bottom of a pane they are already reading.

        Once, and only once. A reader who deliberately pressed `b` back to the
        flow is not dragged off it by the next page that arrives, because this
        never fires twice.
        """
        if self._page_followed or self.show_page or not self._has_page():
            return
        self._page_followed = True
        self.show_page = True
        self._reset_scroll()

    def _toggle_page(self) -> None:
        """Flip the right pane between the flow and the page the browser is on.

        The scroll offset is reset on the way, because the two views have
        different heights and an offset that was the bottom of one is somewhere
        arbitrary in the other. The follow-the-run rule re-pins the flow to its
        tail on the next frame, which is where a live run should be.
        """
        self.show_page = not self.show_page
        self._reset_scroll()

    # ------------------------------------------------------------------
    # Menu helpers
    # ------------------------------------------------------------------
    def _targets(self) -> list[str]:
        return COMMAND_TARGETS.get(self.family or "", [])

    def _current_options(self) -> list[str]:
        return FAMILIES if self.menu_level == "family" else self._targets()

    def _move(self, delta: int) -> None:
        n = len(self._current_options())
        if n:
            self.selected = (self.selected + delta) % n

    def _menu_mouse(self, event):
        if (self.show_btw or self.state != MENU or self._usage_report is not None
                or event.event_type not in (MouseEventType.MOUSE_DOWN, MouseEventType.MOUSE_UP)):
            return False
        from prompt_toolkit.formatted_text import to_formatted_text
        from prompt_toolkit.formatted_text.utils import split_lines

        self._status_input = False
        self._input_notice = ""
        self.slash_menu.dismiss()
        self.app.layout.focus(self.body)
        lines = list(split_lines(to_formatted_text(self._render_body())))
        row = event.position.y
        if 0 <= row < len(lines):
            label = "".join(fragment[1] for fragment in lines[row]).strip(" │┃▸")
            options = self._current_options()
            if label in options:
                self.selected = options.index(label)
                if event.event_type == MouseEventType.MOUSE_UP:
                    self._select()
        self.app.invalidate()
        return True

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------
    def _enter_menu(self) -> None:
        self._status_request = None
        self._usage_report = None
        self._status_input = False
        self.state = MENU
        self.menu_level = "family"
        self.selected = 0
        self.family = None
        self.target = None
        # The last run's page goes with the last run: this run has not reached
        # one yet, and opening the menu onto a view named after a page the
        # browser is no longer on would be showing the reader the previous
        # investigation's application.
        self.show_page = False
        self._page_followed = False
        self._reset_scroll()
        self.app.layout.focus(self.body)

    def _select(self) -> None:
        """Enter/confirm on the current menu row."""
        opts = self._current_options()
        if not opts and self.menu_level == "family":
            return
        if self.menu_level == "family":
            self.family = opts[self.selected]
            if self._targets():           # families with targets -> pick one
                self.menu_level = "target"
                self.selected = 0
            else:                          # e.g. report -> straight to intent
                self.target = None
                self._enter_intent()
        else:
            self.target = self._targets()[self.selected]
            self._enter_intent()

    def _enter_intent(self) -> None:
        self.state = INTENT
        # Looked for here rather than once at startup, so a client the user
        # starts while the wizard is open is found on the next visit rather than
        # after a restart. This is also the screen the answer is shown on.
        self._find_frontend()
        self._reset_scroll()
        self.app.layout.focus(self.input)

    def _find_frontend(self) -> None:
        """Runtime discovers endpoints; the UI never guesses one before submission."""
        self.frontend = None
        self.frontend_hint = "Runtime discovers startup commands and actual application endpoints."

    def _use_suggested_url(self) -> None:
        """Put the discovered client's URL in the box, where it can be seen and edited.

        Not sent: the URL has to reach the Runtime as something the user asked
        for, because the egress guard is fail-closed and correctly refuses a
        host nobody named. Filling the box makes giving that answer one keypress
        instead of a guess, and leaves the text on screen so the user can see
        exactly what will be browsed before pressing Enter.
        """
        if self.frontend is None:
            return
        self.input.text = self.frontend.url
        self.input.buffer.cursor_position = len(self.frontend.url)

    def _back(self) -> None:
        if self.show_btw and self._usage_report is None:
            self._navigate_btw(False)
            return
        if self._usage_report is not None or self._status_input:
            self._status_request = None
            self._usage_report = None
            self._status_input = self.show_btw
            self.app.layout.focus(self.input if self.show_btw or self.state in (INTENT, WORKING, RESULT) else self.body)
            return
        if self.state == INTENT:
            # back to the menu step we came from
            self.state = MENU
            self.menu_level = "target" if self._targets() else "family"
            self.selected = 0
            self.app.layout.focus(self.body)
        elif self.state == MENU and self.menu_level == "target":
            self.menu_level = "family"
            self.selected = 0
        elif self.state == MENU:
            self._status_input = False
            self.app.layout.focus(self.body)
        elif self.state == WORKING:
            s = self.session
            if s and not s.snapshot().get("finished"):
                # Esc during a live run asks the Runtime to stop it.
                s.cancel()
            else:
                # Nothing to cancel. Esc used to fall through to nothing here,
                # which is exactly what made a finished run look frozen: the
                # only way on was Enter, and during a run the input box that
                # receives Enter is not even focused.
                self._show_result()
        elif self.state == RESULT:
            self._enter_menu()

    def _show_result(self) -> None:
        self.state = RESULT
        self.show_page = False
        if self.show_btw:
            self._chat_scroll[False] = 0
        else:
            self._reset_scroll()
        if not self.show_btw and not self.input.text and not self._status_input:
            self.app.layout.focus(self.body)

    def _begin_work(self, raw_intent: str) -> None:
        """Start the run, handing the typed text to the command that parses it."""
        self.raw_intent = raw_intent
        self.show_report = False
        self._diagram = None
        self._session_account_id = self._account_id
        self._status_request = None
        self._usage_report = None
        self._status_input = False
        self.session = TuiSession(
            family=self.family or "investigate",
            target=self.target,
            # The text is not decoration: the command runs it through
            # parse_intent, so a target or URL typed here is investigated
            # exactly as if it had been picked from the menu.
            intent_text=raw_intent,
            repo_path=self.repo_path,
            on_change=self._invalidate,
            # A run planned deterministically and executed against a warm
            # browser finishes faster than a person can read it: the trace
            # arrives as one already-complete column, which reads as a replay
            # rather than as work. TuiSession holds only the *narration* between
            # steps — every step has already executed and been recorded before
            # the pause begins — so this changes what the screen looks like and
            # nothing about what the run did. See TuiSession._pace.
            pace=0.45,
        )
        self.state = WORKING
        self.show_page = False
        self._page_followed = False
        self._reset_scroll()
        self._input_notice = ""
        self.app.layout.focus(self.input)
        self.session.start()

    def _invalidate(self) -> None:
        # Called from the worker thread; invalidate() is thread-safe.
        try:
            self._sync_finished()
            self.app.invalidate()
        except Exception:
            pass

    def _sync_finished(self) -> None:
        """Move to the result the moment the run ends.

        The worker calls this on every event, so the last one — the one that
        flips `finished` — is what carries the screen across. Waiting for the
        user to discover that Enter reveals the report is what made a completed
        run indistinguishable from a hung one.
        """
        if self.state != WORKING or self.session is None:
            return
        snap = self.session.snapshot()
        if not snap.get("finished"):
            return
        self._show_result()
        self._record_history(snap)
        from wizard.cli.parser.intent_parser import parse_intent
        architecture_requested = self.session.family == "investigate" and "architecture" in parse_intent(
            self.session.intent_text, "investigate", menu_target=self.session.target or None).targets
        if architecture_requested and snap.get("status") in {"completed", "incomplete", "failed"}:
            self._prepare_diagram(self.session)
        if not self.show_btw:
            self._reset_scroll()
        def focus_result():
            # Preserve report shortcuts when no draft is being edited. A
            # finishing worker must never move focus away from typed text.
            if not self.show_btw and self.state == RESULT and not self.input.text and not self._status_input:
                pending = getattr(self, "_diagram", None)
                self.app.layout.focus(self.input if pending and pending[0] is self.session and pending[1] is not None else self.body)
        if self.app.loop:
            self.app.loop.call_soon_threadsafe(focus_result)
        else:
            focus_result()

    def _prepare_diagram(self, session):
        def run():
            from wizard.cli.runtime_client.architecture import prepare
            try:
                graph = prepare(session.investigation_id)
                from wizard.cli.account_login import account_origin
                destination = account_origin()
                message = (f"Upload architecture to {destination}?\n\n"
                           f"Graph status: {graph['status']}\n\n"
                           f"Repository: {graph['repository_name']} | Groups: {len(graph.get('groups', []))} | Nodes: {len(graph['nodes'])} | "
                           f"Relationships: {len(graph['relationships'])} | Evidence: {len(graph['evidence'])}\n\n"
                           "Uploads labels, descriptions, relative file paths, and evidence references. "
                           "Includes short verified content predicates when available; literal module references are observed and reasoned relationships are marked inferred. "
                           "No full source files are uploaded.\n\n"
                           "Type yes to consent or no to keep results local.")
                ready = (session, graph, message, destination)
            except Exception:
                ready = (session, None, "Architecture upload unavailable. Check account configuration and local evidence. Local results are preserved.", None)
            if self.session is session:
                self._diagram = ready
                def focus():
                    if self.session is session and self.state == RESULT and ready[1]:
                        self.app.layout.focus(self.input)
                    self.app.invalidate()
                if self.app.loop:
                    self.app.loop.call_soon_threadsafe(focus)
        threading.Thread(target=run, name="architecture-summary", daemon=True).start()

    def _answer_diagram(self, answer):
        pending = getattr(self, "_diagram", None)
        if not pending or pending[0] is not self.session or pending[1] is None:
            return False
        if answer.lower() not in {"yes", "no"}:
            return False
        session, graph, _, destination = pending
        self._diagram = (session, None, "Keeping architecture results local." if answer.lower() == "no" else "Saving architecture...", destination)
        if answer.lower() == "yes":
            def run():
                from wizard.cli.runtime_client.architecture import upload
                from wizard.cli.account_login import account_origin
                try:
                    if account_origin() != destination:
                        raise ValueError("Upload destination changed; investigate again to review consent.")
                    message = upload(graph, consent=True)
                except Exception as exc:
                    from wizard.cli.tui.session import sanitize_terminal
                    message = "Architecture upload failed. " + sanitize_terminal(str(exc)) + " Local results are preserved."
                if self.session is session:
                    self._diagram = (session, None, message, destination)
                    self.app.invalidate()
            threading.Thread(target=run, name="architecture-upload", daemon=True).start()
        return True

    def _record_history(self, snap: dict) -> None:
        """Append this run to the file the top panel reads.

        Once per run, guarded by the state rather than by the caller: every
        event after the last one would otherwise append another row for the same
        investigation, and the panel would fill up with one run repeated. The
        guard is that this is only reachable from WORKING.

        Best-effort, and silently so — `record_run` swallows its own IO errors.
        A history file is not worth failing a finished investigation over, and
        the panel already has a line for the case where nothing was recorded.
        """
        history.record_run(
            family=self.family or "investigate",
            target=self.target,
            intent=self.raw_intent,
            status=snap.get("status", "completed"),
        )
        # The panel is now a frame out of date, so the next render must not
        # serve it the cached one.
        self._static_frames.pop("top", None)


    # ------------------------------------------------------------------
    # Input accept (Enter in the text box)
    # ------------------------------------------------------------------
    def _notice_height(self):
        width = max(20, self._geometry()[0])
        rows = sum(max(1, (len(line) + width - 1) // width) for line in self._input_notice.split("\n"))
        return min(4, max(1, rows))

    def _start_account_login(self):
        with self._account_state_lock:
            self._start_account_login_locked()

    def _start_account_login_locked(self):
        if self._account_logout_running:
            self._input_notice = "Logout is in progress. Run /login when it finishes."
            return
        if self._account_login and self._account_login.running:
            self._input_notice = "Account login is already active. Paste the website code or /cancel-login."
        else:
            from wizard.cli.account_login import LoginWorker
            operation = self._auth_operation = object()
            def notify(message):
                with self._account_state_lock:
                    if self._exiting or self._auth_operation is not operation:
                        return
                    self._usage_report = message
                    self.app.invalidate()
            self._account_login = LoginWorker(notify)
            def authenticated(account):
                with self._account_state_lock:
                    if self._auth_operation is operation:
                        self._set_account(account)
            self._account_login.on_authenticated = authenticated
            self._account_login.start()
            self._input_notice = "Account login: paste the website code here; /cancel-login cancels."
        self._status_input = True
        self.input.text = ""
        self.app.layout.focus(self.input)

    def _start_account_logout(self):
        with self._account_state_lock:
            self._start_account_logout_locked()

    def _start_account_logout_locked(self):
        import threading

        if self._account_logout_running:
            return
        operation = self._auth_operation = object()
        self._account_revision += 1
        self._status_request = None
        if self._account_login:
            self._account_login.cancel()
        self._account_logout_running = True
        self._input_notice = "Logging out..."
        self._usage_report = None

        def run():
            from wizard.cli.account_login import LoginError
            from wizard.cli.account_logout import logout
            from wizard.cli.account_storage import StorageError

            try:
                message = logout(on_removed=lambda: self._set_account(None))
            except (LoginError, StorageError) as exc:
                message = "Logout failed. " + str(exc)
            finally:
                self._account_logout_running = False
            with self._account_state_lock:
                if not self._exiting and self._auth_operation is operation:
                    self._input_notice = message
                    self.app.invalidate()

        threading.Thread(target=run, name="account-logout", daemon=True).start()

    def _set_account(self, account):
        with self._account_state_lock:
            self._set_account_locked(account)

    def _set_account_locked(self, account):
        if self._exiting:
            return
        from wizard.cli.tui.session import sanitize_terminal

        name = (account or {}).get("full_name") or (account or {}).get("email")
        self._account_id = (account or {}).get("id")
        self._status_request = None
        self._account_name = sanitize_terminal(name or "default user").replace("\n", " ").replace("\r", " ")
        self._account_revision += 1
        self.app.invalidate()

    def _load_account_identity(self):
        """Check persisted authentication off the UI thread; never open a browser."""
        import threading

        revision = self._account_revision
        operation = self._auth_operation

        def load():
            from wizard.cli.account_login import LoginError, LoginFlow
            from wizard.cli.account_storage import StorageError

            flow = None
            try:
                flow = LoginFlow()
                account = flow.authenticated_account(flow.store.load())
            except (LoginError, StorageError):
                return
            finally:
                if flow:
                    flow.close()
            valid = not flow.cancelled()
            with self._account_state_lock:
                if self._account_revision == revision and self._auth_operation is operation and valid:
                    self._set_account(account)

        threading.Thread(target=load, name="account-identity", daemon=True).start()

    def _request_exit(self) -> None:
        if self._exiting:
            return
        self._exiting = True
        if self.side_chat:
            self.side_chat.close()
        self._status_request = None
        if self._account_login:
            self._account_login.cancel()
        if self.session:
            self.session.cancel()
        self.app.exit()

    def _on_accept(self, buff) -> bool:
        text = buff.text
        command = text.strip()
        if self.state == RESULT and not self.show_btw and self._answer_diagram(command):
            return False
        if command == "/exit":
            self._request_exit()
            return False
        if command == "/btw" or command.startswith("/btw "):
            action = command[4:].strip()
            if action in ("main", "return", "new"):
                buff.text = ""
                if action == "new":
                    if self.side_chat and self.side_chat.snapshot()["pending"]:
                        self._input_notice = "Wait for the current side response before starting a new conversation."
                        return False
                    if self.side_chat:
                        self.side_chat.close()
                    self.side_chat = None
                    self._chat_drafts[True] = ""
                    self._chat_scroll[True] = 0
                self._navigate_btw(action != "main")
            elif action in ("copy", "copy all"):
                if self.show_btw:
                    self._copy_btw(action == "copy all")
                else:
                    self._input_notice = "Open your side conversation to copy an answer."
                buff.text = ""
            else:
                buff.text = ""
                self._navigate_btw(True)
                if action:
                    self._submit_btw(action)
            return True
        if command == "/cancel-login":
            if self._account_login:
                self._account_login.cancel()
            self._input_notice = "Account login cancellation requested."
            buff.text = ""
            return False
        if command == "/login":
            self._start_account_login()
            buff.text = ""
            return False
        if command == "/logout":
            self._start_account_logout()
            buff.text = ""
            return False
        if self.show_btw and command not in SLASH_COMMANDS:
            return self._submit_btw(text)
        if self._account_login and self._account_login.running and not command.startswith("/"):
            self._account_login.submit(command)
            buff.text = ""
            return False
        # Reject command-shaped typos without treating paths, dates or embedded
        # slashes as commands. Ordinary side-chat text is handled above.
        import re
        if re.match(r"^/[a-zA-Z-]+(?:\s|$)", command) and command not in SLASH_COMMANDS:
            self._input_notice = "Unknown command. Available: " + ", ".join(SLASH_COMMANDS)
            return True
        if text.strip() == "/status":
            self._status_input = False
            buff.text = ""
            self._usage_report = "Loading persisted usage..."
            token = object()
            self._status_request = token
            self.app.layout.focus(self.body)
            self._reset_scroll()
            own_run = self._owns_usage_session()
            run_id = self.session.investigation_id if self.session and own_run else None
            pending_run = bool(self.session and own_run and self.session.running and not run_id)
            import threading
            def load():
                from wizard.cli.display.usage import format_status
                from wizard.cli.runtime_client.usage import status
                try:
                    data = status(run_id=run_id) if run_id else status()
                    if pending_run:
                        data = {**data, "current_run": None, "current_run_pending": True}
                    report = format_status(data)
                except Exception as exc:
                    from wizard.cli.tui.session import _safe_display
                    report = _safe_display(str(exc)) or "Usage unavailable: check runtime and PostgreSQL configuration"
                with self._account_state_lock:
                    if self._status_request is token:
                        self._usage_report = report + "\n\nEsc to return"
                        self.app.invalidate()
            threading.Thread(target=load, name="usage-status", daemon=True).start()
            return False
        if self._status_input:
            self._status_input = False
        if self.state == INTENT:
            self._begin_work(text)
        elif self.state == WORKING:
            self._sync_finished()
            self._input_notice = "Run active; draft retained. /status shows usage; /exit cancels and quits."
            return True
        elif self.state == RESULT:
            self._input_notice = "Draft retained. Esc returns to the command menu."
            return True
        elif self.state == MENU:
            if self.modern_ui and command:
                self.family, self.target = "verify", "runtime"
                self._enter_intent()
                self._input_notice = "Ready to check this goal. Submit again to start, or edit it first."
                return True
            self._status_input = True
            self._input_notice = "Choose a command from the menu; draft retained."
            return True
        return False  # never keep the text; we manage it ourselves

    def _navigate_btw(self, show):
        from wizard.cli.tui.side_chat import SideChat
        if show and self.side_chat is None:
            self.side_chat = SideChat(self._invalidate, session_id=self._btw_session_id)
        if show != self.show_btw:
            self._chat_drafts[self.show_btw] = self.input.text
            self._chat_scroll[self.show_btw] = self.scroll
            self.show_btw = show
            self.input.text = self._chat_drafts[show]
            self.scroll = self._chat_scroll[show]
        self._usage_report = None
        self._status_request = None
        self._input_notice = ""
        self.input_frame.title = "/btw conversation" if show else "Intent / command"
        commands = dict(SLASH_COMMANDS)
        if show:
            commands.update(BTW_COMMANDS)
        elif self.side_chat:
            commands["/btw return"] = "Return to your conversation"
        self.input.completer.commands = commands
        self.slash_menu.open()
        self._status_input = show
        self.app.layout.focus(self.input)
        self.app.invalidate()

    def _submit_btw(self, text):
        if not text.strip():
            self._input_notice = "Type a question for your side conversation."
            return True
        if not self.side_chat.submit(text):
            self._input_notice = "A side response is pending; your draft is retained."
            self.input.text = text
            return True
        self.input.text = ""
        self._input_notice = ""
        return False

    def _copy_btw(self, all_messages=False):
        from wizard.cli.tui.clipboard import ClipboardError, write_text
        messages = self.side_chat.snapshot()["messages"] if self.side_chat else []
        answer = ("\n\n".join(m["role"] + ":\n" + m["content"] for m in messages)
                  if all_messages else next((m["content"] for m in reversed(messages) if m["role"] == "assistant"), ""))
        if not answer:
            self._input_notice = "No side-conversation answer to copy yet."
            return
        try:
            write_text(answer)
            self._input_notice = "Copied conversation." if all_messages else "Copied answer."
        except ClipboardError as exc:
            self._input_notice = str(exc)

    # ------------------------------------------------------------------
    # Key bindings
    # ------------------------------------------------------------------
    def _copy_intent(self, cut=False):
        from wizard.cli.tui.clipboard import ClipboardError, write_text

        buff = self.input.buffer
        if not buff.selection_state:
            return
        _, data = buff.document.cut_selection()
        if not data.text:
            return
        try:
            write_text(data.text)
        except ClipboardError as exc:
            self._input_notice = str(exc)
            return
        self.app.clipboard.set_data(data)
        if cut:
            buff.cut_selection()

    def _paste_intent(self, text=None):
        from wizard.cli.tui.clipboard import ClipboardError, read_text

        if text is None:
            try:
                text = read_text()
            except ClipboardError as exc:
                self._input_notice = str(exc)
                return
        if not text:
            return
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        self.app.layout.focus(self.input)
        if self.state == MENU:
            self._status_input = True
        buff = self.input.buffer
        if buff.selection_state:
            buff.cut_selection()
        # Pasting always edits the draft; it never submits commands or intent.
        buff.insert_text(text)
        self.app.invalidate()

    def _bindings(self) -> KeyBindings:
        kb = KeyBindings()
        @kb.add("f6")
        @kb.add("escape", "b")
        def navigate_conversation(event):
            self._navigate_btw(not self.show_btw)
        @kb.add("/", filter=Condition(lambda: not self.app.layout.has_focus(self.input)))
        def open_status(event):
            self._status_input = True
            self.input.buffer.insert_text("/")
            self.app.layout.focus(self.input)

        typing = Condition(lambda: self._status_input or self.state in (INTENT, WORKING) or self.app.layout.has_focus(self.input))
        navigating = Condition(lambda: not self.show_btw and self.state == MENU and not self._status_input
                               and self._usage_report is None
                               and not self.app.layout.has_focus(self.input))
        # The box has something to scroll in every state except the ones that
        # own the keyboard.
        scrollable = Condition(lambda: self.show_btw or self.state in (WORKING, RESULT) or self._usage_report is not None)
        pane_keys = scrollable & Condition(lambda: not self.app.layout.has_focus(self.input))

        @kb.add("c-c")
        def _(event):
            if self.app.layout.has_focus(self.input) and self.input.buffer.selection_state:
                self._copy_intent()
            else:
                self._request_exit()

        editing = Condition(lambda: self.app.layout.has_focus(self.input))

        @kb.add("c-a", filter=editing)
        def select_intent(event):
            buff = self.input.buffer
            if buff.text:
                buff.cursor_position = 0
                buff.start_selection()
                buff.selection_state.enter_shift_mode()
                buff.cursor_position = len(buff.text)

        @kb.add("c-insert", filter=editing)
        def copy_intent(event):
            self._copy_intent()

        @kb.add("c-x", filter=editing)
        def cut_intent(event):
            self._copy_intent(cut=True)

        @kb.add("c-v")
        @kb.add("s-insert")
        def paste_intent(event):
            self._paste_intent()

        @kb.add(Keys.BracketedPaste)
        def terminal_paste_intent(event):
            self._paste_intent(event.data)

        # q quits only when not typing: in the box, `q` is a letter.
        @kb.add("q", filter=~typing)
        def _(event):
            self._request_exit()


        @kb.add("up", filter=navigating)
        @kb.add("k", filter=navigating)
        def _(event):
            self._move(-1)

        @kb.add("down", filter=navigating)
        @kb.add("j", filter=navigating)
        def _(event):
            self._move(1)

        @kb.add("enter", filter=navigating)
        def _(event):
            self._select()

        # --- right pane scrolling -------------------------------------
        # Bound in the states where the text box is not taking input, so these
        # reach the pane instead of moving a cursor in a box nobody is typing in.
        @kb.add("up", filter=pane_keys)
        @kb.add("k", filter=pane_keys)
        def _(event):
            self._scroll_by(-1)

        @kb.add("down", filter=pane_keys)
        @kb.add("j", filter=pane_keys)
        def _(event):
            self._scroll_by(1)

        @kb.add("pageup", filter=scrollable)
        @kb.add("c-b", filter=scrollable)
        def _(event):
            _, page = self._scroll_bounds()
            self._scroll_by(-page)

        @kb.add("pagedown", filter=scrollable)
        @kb.add("c-f", filter=scrollable)
        def _(event):
            _, page = self._scroll_bounds()
            self._scroll_by(page)

        @kb.add("home", filter=pane_keys)
        def _(event):
            self.scroll = 0
            # Jumping to the top is a deliberate scroll away from the tail; say
            # so, or the next frame of a live run pulls the view straight back.
            self._pinned_top = 0

        @kb.add("end", filter=pane_keys)
        def _(event):
            top, _ = self._scroll_bounds()
            self.scroll = top
            self._pinned_top = top

        # The wheel is not bound here: prompt_toolkit delivers a scroll to the
        # Window under the pointer and scrolls it itself, which is why the
        # offset above is read back off the Window rather than owned by us.

        @kb.add("f3", filter=Condition(lambda: self.state in (WORKING, RESULT)))
        def _(event):
            self._report_action("view")

        @kb.add("f6", filter=Condition(lambda: self.state in (WORKING, RESULT)))
        def _(event):
            self._report_action("copy")

        @kb.add("f4", filter=Condition(lambda: self.state == RESULT))
        def _(event):
            self._report_action("open")

        @kb.add("f5", filter=Condition(lambda: self.state == RESULT))
        def _(event):
            self._report_action("rerun")

        # r is the explicit "do it again" on the result screen.
        @kb.add("r", filter=Condition(lambda: not self.show_btw and self.state == RESULT and not self.app.layout.has_focus(self.input)))
        def _(event):
            self._enter_menu()

        # b flips to the page the browser is on. Offered only when there is one
        # to show — and always available on the page view itself, or a reader
        # who opened it before the run went back to the flow would be stuck
        # looking at a page that is no longer there.
        @kb.add("b", filter=Condition(
            lambda: not self.show_btw and self.state in (WORKING, RESULT) and not self.app.layout.has_focus(self.input) and (self.show_page or self._has_page())
        ))
        def _(event):
            self._toggle_page()

        # Not eager: prompt_toolkit must disambiguate a lone Esc from the ESC
        # prefix of arrow-key sequences, or menu navigation breaks.
        @kb.add("escape")
        def _(event):
            self._back()

        # F2 fills the box with the discovered client's URL. Bound rather than
        # automatic because the URL has to be the user's own request: the
        # Runtime's egress guard is fail-closed, and a target the wizard added
        # on its own would either be refused as unnamed or quietly widen what
        # this run is allowed to reach.
        @kb.add("f2", filter=Condition(lambda: not self.show_btw and self.state == INTENT))
        def _(event):
            self._use_suggested_url()

        slash_menu = Condition(lambda: self.slash_menu.visible)

        @kb.add("up", filter=slash_menu)
        def slash_up(event):
            self.slash_menu.move(-1)

        @kb.add("down", filter=slash_menu)
        def slash_down(event):
            self.slash_menu.move(1)

        @kb.add("pageup", filter=slash_menu)
        def slash_page_up(event):
            self.slash_menu.move(-max(1, self.slash_menu.height()))

        @kb.add("pagedown", filter=slash_menu)
        def slash_page_down(event):
            self.slash_menu.move(max(1, self.slash_menu.height()))

        @kb.add("enter", filter=slash_menu)
        def slash_accept(event):
            self.slash_menu.apply()
            # Use the typed-command handler, including side-chat navigation.
            self.input.buffer.validate_and_handle()

        @kb.add("tab", filter=Condition(lambda: self.app.layout.has_focus(self.input)
                                      and bool(self.slash_menu.entries)))
        def slash_complete(event):
            if self.slash_menu.visible:
                self.slash_menu.apply()  # Fill only; leave the composer editable.
            else:
                self.slash_menu.open()

        @kb.add("escape", filter=slash_menu)
        def slash_dismiss(event):
            self.slash_menu.dismiss()  # Preserve draft/cursor and do not cancel a run.

        return kb

    # ------------------------------------------------------------------
    def run(self) -> None:
        self._load_account_identity()
        try:
            self.app.run()
        finally:
            if self.side_chat:
                self.side_chat.close()


def run_tui(repo_path: str | None = None) -> None:
    """Launch the interactive Wizard TUI (bare `wizard`, or `wizard <path>`).

    `repo_path` is the repository to investigate. Given, it is the folder named
    on the command line; omitted, it is where the user launched from. It is
    checked before anything is started, so a typo'd path is a sentence rather
    than three services coming up to investigate nothing.

    The services come up first — started if they are not already listening,
    adopted if they are — and the endpoints they ended up on are exported, so
    a bare `wizard` is already connected and nothing has to be started by hand.

    Only the Runtime Engine is required. The planner and the agents are seams:
    a run without them still works, and `seams.resolved` says so in the flow,
    which is what keeps an unwired run from looking like a wired one.
    """
    if os.environ.get("WIZARD_UI", "textual") == "textual":
        try:
            from wizard.cli.tui.textual_app import run_native
        except ModuleNotFoundError as exc:
            if exc.name != "textual":
                raise
            print('Wizard needs its updated UI dependencies. In your Wizard environment run: pip install -e ".[tui]"')
            return
        run_native(project=repo_path)
        return

    if repo_path:
        target = os.path.abspath(os.path.expanduser(repo_path))
        if not os.path.isdir(target):
            print(
                f"\n{repo_path} is not a directory, so there is nothing there to "
                "investigate.\nPass the folder that holds the project, "
                "e.g. `wizard C:/path/to/project`.",
                flush=True,
            )
            return

    from wizard.cli.tui.services import ServiceSupervisor, find_chromium

    # Startup only checks existing browser availability; it never installs one.
    print("agent-browser available" if find_chromium() else "agent-browser unavailable; run npm install -g agent-browser@0.27.0 and agent-browser install", flush=True)

    supervisor = ServiceSupervisor()
    try:
        report = supervisor.ensure_all()
    except BaseException:
        supervisor.stop()
        raise
    for line in report.lines():
        print(line, flush=True)

    if not report.investigation_stack_ok:
        print(
            "\nThe current Wizard Runtime service must be "
            "available before an investigation can start.\nResolve the [x] service "
            "shown above, then run wizard again. Details are also in "
            f"{supervisor.log_dir}.",
            flush=True,
        )
        supervisor.stop()
        return

    os.environ.update(supervisor.apply_env())
    tui = WizardTUI(repo_path=repo_path)
    try:
        tui.run()
    finally:
        if tui.session:
            tui.session.shutdown(timeout=2)
        # Only the children this run started; anything adopted outlives us.
        stopped = supervisor.stop()
        if stopped:
            print(f"stopped: {', '.join(stopped)}", flush=True)
