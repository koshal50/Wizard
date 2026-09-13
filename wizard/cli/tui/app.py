"""The Wizard TUI application — a single prompt_toolkit full-screen app.

prompt_toolkit owns the event loop, the alternate screen, and all keyboard
input; that single ownership is what keeps the screen from breaking and lets an
input box stay live *during* an investigation. Rich only builds the content of
the upper region (see widgets.py), which we rasterize to ANSI each frame.

State machine:  SPLASH → MENU → INTENT → WORKING → RESULT
A ~0.08s refresh drives the pulsing dot and verb animations; a background worker
(session.py) streams real engine events and calls `app.invalidate()` to redraw.
"""

from __future__ import annotations

import os
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
    frame,
    intent_right,
    menu_right,
    render_to_ansi,
    result_right,
    splash_right,
    working_right,
)

# Screen states
SPLASH, MENU, INTENT, WORKING, RESULT = "splash", "menu", "intent", "working", "result"

# Command families offered in the menu, sourced live from the canonical
# registry (no duplicate list). Order is stable/insertion order.
FAMILIES = list(COMMAND_TARGETS.keys())


class WizardTUI:
    """Owns all mutable UI state and wires prompt_toolkit together."""

    def __init__(self) -> None:
        self.state = SPLASH
        self._start = time.monotonic()

        # Menu selection state
        self.menu_level = "family"          # "family" | "target"
        self.selected = 0
        self.family: str | None = None
        self.target: str | None = None

        self.session: TuiSession | None = None

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
        root = HSplit(
            [
                self.body,
                ConditionalContainer(self.input_frame, filter=input_visible),
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
            return 80

    # ------------------------------------------------------------------
    # Content rendering (per frame)
    # ------------------------------------------------------------------
    def _render_body(self):
        w = self._width()
        t = self._t()

        if self.state == SPLASH:
            right = splash_right()

        elif self.state == MENU:
            options = FAMILIES if self.menu_level == "family" else self._targets()
            right = menu_right(self.menu_level, options, self.selected, self.family)

        elif self.state == INTENT:
            right = intent_right(self.family, self.target)

        elif self.state == WORKING:
            s = self.session
            if s:
                snap = s.snapshot()
                bullets = s.snapshot_activity()
                right = working_right(snap, bullets, t)
            else:
                right = splash_right()

        elif self.state == RESULT:
            s = self.session
            snap = s.snapshot() if s else {}
            right = result_right(snap.get("status", ""), snap.get("report_markdown", ""))

        else:
            right = splash_right()

        return render_to_ansi(frame(t, right), w)

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
            elif s and s.finished:
                self.state = RESULT
                self.app.layout.focus(self.body)
        elif self.state == RESULT:
            self._enter_menu()

    def _begin_work(self, raw_intent: str) -> None:
        """Build the session and start streaming via the service functions."""
        self.session = TuiSession(
            family=self.family,
            target=self.target,
            on_change=self._invalidate,
        )
        self.state = WORKING
        self.app.layout.focus(self.input)
        self.session.start()
        # Non-empty free-text intent is queued locally (engine has no raw-intent
        # field yet) so it is visible and preserved — see plan "wire later".
        if raw_intent.strip():
            self.session.add_steering(raw_intent)

    def _invalidate(self) -> None:
        # Called from the worker thread; invalidate() is thread-safe.
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
        return False  # never keep the text; we manage it ourselves

    # ------------------------------------------------------------------
    # Key bindings
    # ------------------------------------------------------------------
    def _bindings(self) -> KeyBindings:
        kb = KeyBindings()

        typing = Condition(lambda: self.state in (INTENT, WORKING))
        navigating = Condition(lambda: self.state == MENU)
        on_splash = Condition(lambda: self.state == SPLASH)

        @kb.add("c-c")
        def _(event):
            event.app.exit()

        # q quits only when not typing and not on the splash (there it advances).
        @kb.add("q", filter=~typing & ~on_splash)
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

        # Not eager: prompt_toolkit must disambiguate a lone Esc from the ESC
        # prefix of arrow-key sequences, or menu navigation breaks.
        @kb.add("escape")
        def _(event):
            if self.state == SPLASH:
                self._enter_menu()
            else:
                self._back()

        # Any key dismisses the splash.
        @kb.add(Keys.Any, filter=on_splash)
        def _(event):
            self._enter_menu()

        return kb

    # ------------------------------------------------------------------
    def run(self) -> None:
        self.app.run()


def run_tui() -> None:
    """Launch the interactive Wizard TUI (bare `wizard`)."""
    WizardTUI().run()
