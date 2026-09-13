"""The Wizard TUI application — a single prompt_toolkit full-screen app.

Layout:
    ╭── wizard v0.2.0 ──────────┬──────────────────╮
    │   Welcome back Koshal!     │ Recent activity   │  ← always visible
    │   [wizard pixel art]       │ ...               │
    │   v0.2.0 · API Usage ...   │                   │
    ╰────────────────────────────┴──────────────────╯

    ╭───────────────────────────────────────────────╮
    │   [content changes by state]                   │  ← one persistent box
    ╰───────────────────────────────────────────────╯

    › [input prompt]

No SPLASH state — the top panel IS the welcome, and the command menu is
immediately visible below it. States: MENU → INTENT → WORKING → RESULT.
"""

from __future__ import annotations

import time

from prompt_toolkit.application import Application
from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.keys import Keys
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import ConditionalContainer, HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.styles import Style
from prompt_toolkit.widgets import Frame, TextArea

from wizard.cli.parser.command_parser import COMMAND_TARGETS
from wizard.cli.tui.session import TuiSession
from wizard.cli.tui.widgets import (
    command_box_intent,
    command_box_menu,
    command_box_result,
    command_box_working,
    render_to_ansi,
    top_panel,
)

# Screen states (no SPLASH — menu is immediately visible)
MENU, INTENT, WORKING, RESULT = "menu", "intent", "working", "result"

# Command families offered in the menu, sourced live from the canonical
# registry (no duplicate list). Order is stable/insertion order.
FAMILIES = list(COMMAND_TARGETS.keys())


class WizardTUI:
    """Owns all mutable UI state and wires prompt_toolkit together."""

    def __init__(self) -> None:
        self.state = MENU
        self._start = time.monotonic()

        # Menu selection state
        self.menu_level = "family"          # "family" | "target"
        self.selected = 0
        self.family: str | None = None
        self.target: str | None = None
        self.raw_intent: str = ""           # last intent text for history

        self.session: TuiSession | None = None

        # Cache the top panel renderable (only changes when history updates)
        self._top_panel_cache = None
        self._top_panel_dirty = True

        # --- input box (used in INTENT and WORKING) ---
        self.input = TextArea(
            prompt="› ",
            multiline=False,
            wrap_lines=False,
            accept_handler=self._on_accept,
            height=1,
        )
        self.input_frame = Frame(self.input, style="class:inputbox")

        # --- main content region ---
        self.body = Window(
            content=FormattedTextControl(self._render_body, focusable=True),
            wrap_lines=False,
        )

        input_visible = Condition(lambda: self.state in (INTENT, WORKING))
        hint_visible = Condition(lambda: self.state == MENU)

        # Hint line at the bottom
        self.hint = Window(
            content=FormattedTextControl(lambda: "  ? for shortcuts"),
            height=1,
        )

        root = HSplit(
            [
                self.body,
                ConditionalContainer(self.input_frame, filter=input_visible),
                ConditionalContainer(self.hint, filter=hint_visible),
            ]
        )

        self.app: Application = Application(
            layout=Layout(root, focused_element=self.body),
            key_bindings=self._bindings(),
            style=Style.from_dict(
                {
                    "inputbox": "#5b2d7a",           # violet frame border
                    "inputbox frame.border": "#5b2d7a",
                }
            ),
            full_screen=True,
            mouse_support=False,
            refresh_interval=0.08,  # drives the animations
        )

    # ------------------------------------------------------------------
    # Timing / geometry
    # ------------------------------------------------------------------
    def _t(self) -> float:
        return time.monotonic() - self._start

    def _width(self) -> int:
        try:
            return self.app.output.get_size().columns
        except Exception:
            return 120

    # ------------------------------------------------------------------
    # Content rendering (per frame)
    # ------------------------------------------------------------------
    def _render_body(self):
        from rich.console import Group
        w = self._width()
        t = self._t()

        # Top panel (always visible)
        header = top_panel()

        # Command box (content changes by state)
        if self.state == MENU:
            options = FAMILIES if self.menu_level == "family" else self._targets()
            box = command_box_menu(self.menu_level, options, self.selected, self.family)

        elif self.state == INTENT:
            box = command_box_intent(self.family, self.target)

        elif self.state == WORKING:
            s = self.session
            if s:
                snap = s.snapshot()
                bullets = s.snapshot_activity()
                box = command_box_working(snap, bullets, t)

                # Auto-transition to RESULT when finished
                if snap.get("finished") and not snap.get("running"):
                    self.state = RESULT
                    self.app.layout.focus(self.body)
                    # Record to history
                    self._record_history(snap.get("status", "completed"))
            else:
                box = command_box_menu("family", FAMILIES, 0, None)

        elif self.state == RESULT:
            s = self.session
            snap = s.snapshot() if s else {}
            box = command_box_result(snap.get("status", ""), snap.get("report_markdown", ""))

        else:
            box = command_box_menu("family", FAMILIES, 0, None)

        return render_to_ansi(Group(header, box), w)

    # ------------------------------------------------------------------
    # History recording
    # ------------------------------------------------------------------
    def _record_history(self, status: str) -> None:
        """Record this run in the activity history file."""
        try:
            from wizard.cli.tui.history import record_run
            record_run(
                family=self.family or "?",
                target=self.target,
                intent=self.raw_intent,
                status=status,
            )
            self._top_panel_dirty = True
        except Exception:
            pass  # history is non-critical

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

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------
    def _enter_menu(self) -> None:
        self.state = MENU
        self.menu_level = "family"
        self.selected = 0
        self.family = None
        self.target = None
        self.raw_intent = ""
        self.app.layout.focus(self.body)

    def _select(self) -> None:
        """Enter/confirm on the current menu row."""
        opts = self._current_options()
        if not opts and self.menu_level == "family":
            return
        if self.menu_level == "family":
            self.family = FAMILIES[self.selected]
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
        self.input.text = ""
        self.app.layout.focus(self.input)

    def _back(self) -> None:
        if self.state == INTENT:
            # back to the menu step we came from
            self.state = MENU
            self.menu_level = "target" if self._targets() else "family"
            self.selected = 0
            self.app.layout.focus(self.body)
        elif self.state == MENU and self.menu_level == "target":
            self.menu_level = "family"
            self.selected = 0
        elif self.state == WORKING:
            # Esc during working -> cancel the running investigation
            s = self.session
            if s and not s.finished:
                with s._lock:
                    s.cancelled = True
        elif self.state == RESULT:
            self._enter_menu()

    def _begin_work(self, raw_intent: str) -> None:
        """Build the session and start streaming via the service functions."""
        self.raw_intent = raw_intent
        self.session = TuiSession(
            family=self.family,
            target=self.target,
            on_change=self._invalidate,
        )
        self.state = WORKING
        self.app.layout.focus(self.input)
        self.session.start()
        if raw_intent.strip():
            self.session.add_steering(raw_intent)

    def _invalidate(self) -> None:
        try:
            self.app.invalidate()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Input accept (Enter in the text box)
    # ------------------------------------------------------------------
    def _on_accept(self, buff) -> bool:
        text = buff.text
        if self.state == INTENT:
            self._begin_work(text)
        elif self.state == WORKING:
            s = self.session
            if s and s.finished:
                self.state = RESULT
                self.app.layout.focus(self.body)
            elif s:
                s.add_steering(text)
        return False

    # ------------------------------------------------------------------
    # Key bindings
    # ------------------------------------------------------------------
    def _bindings(self) -> KeyBindings:
        kb = KeyBindings()

        typing = Condition(lambda: self.state in (INTENT, WORKING))
        navigating = Condition(lambda: self.state == MENU)

        @kb.add("c-c")
        def _(event):
            event.app.exit()

        @kb.add("q", filter=~typing)
        def _(event):
            event.app.exit()

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

        @kb.add("escape")
        def _(event):
            self._back()

        return kb

    # ------------------------------------------------------------------
    def run(self) -> None:
        self.app.run()


def run_tui() -> None:
    """Launch the interactive Wizard TUI (bare `wizard`)."""
    WizardTUI().run()
