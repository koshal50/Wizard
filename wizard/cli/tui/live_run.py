"""One live transcript, using the existing session's real event ordering."""
from rich.text import Text
from textual import on
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Button, Static

from wizard.cli.tui.session import sanitize_terminal


class LiveRun(Vertical):
    class Action(Message):
        def __init__(self, action):
            super().__init__()
            self.action = action

    DEFAULT_CSS = """
    LiveRun { height: auto; }
    LiveRun #run-request { height: auto; margin-bottom: 1; color: #8CBFCF; }
    LiveRun #run-flow { height: auto; }
    LiveRun #run-now { height: auto; margin: 1 0; }
    LiveRun #run-report { height: auto; background: transparent; }
    LiveRun #result-actions { height: 4; layout: grid; grid-size: 2; grid-rows: 2 2; }
    LiveRun #result-actions Button { height: 2; width: 1fr; }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._lines = ()
        self._active = False
        self._now = ""
        self._frame = 0
        self._report = ""
        self.output_expanded = False
        self._session = None

    def compose(self):
        yield Static("", id="run-request", markup=False)
        yield Static("", id="run-flow", markup=False)
        yield Static("", id="run-now", markup=False)
        with Horizontal(id="result-actions"):
            yield Button("Open saved report", id="result-open")
            yield Button("Copy start commands", id="result-copy")
            yield Button("Run again", id="result-rerun")
            yield Button("View connections", id="result-diagram")

    def on_mount(self):
        self.query_one("#result-actions").display = False
        self._timer = self.set_interval(.08, self._paint_activity)
        self._timer.pause()

    @on(Button.Pressed)
    def result_action(self, event):
        if event.button.id and event.button.id.startswith("result-"):
            event.stop()
            self.post_message(self.Action(event.button.id.removeprefix("result-")))

    def show_request(self, family, target, intent):
        label = " ".join(part for part in (family, target) if part)
        self.query_one("#run-request", Static).update(sanitize_terminal(label + ("\n" + intent if intent else ""))[:1200])

    def connecting(self):
        self._now, self._active = "Connecting to local services", True
        self._timer.resume()
        self._paint_activity()

    def stop_activity(self, message):
        self._now, self._active = message, False
        self._timer.pause()
        self._paint_activity()

    def _paint_activity(self):
        text = Text()
        if self._active:
            palette = ("#33434A", "#628A9B", "#B6DDE5", "#E7A168", "#754336")
            moving = getattr(self.app, "motion_enabled", True)
            for cell in range(4):
                text.append(" ", style="on " + palette[(cell + (self._frame if moving else 0)) % len(palette)])
            text.append("  ")
        text.append(self._now, style="#8CBFCF")
        if self._active and getattr(self.app, "motion_enabled", True) and self._now:
            # A light sweep through the current action, never fake progress.
            position = self._frame % (len(self._now) + 10)
            for index in range(max(0, position - 5), min(len(self._now), position + 1)):
                text.stylize("bold #E7A168", index, index + 1)
            self._frame += 1
        self.query_one("#run-now", Static).update(text)
        self.app.refresh_usage_footer()

    def toggle_output(self):
        self.output_expanded = not self.output_expanded
        self._lines = ()
        if self._session:
            self.display_session(self._session)
        return self.output_expanded

    def display_session(self, session):
        self._session = session
        state = session.snapshot()
        lines = tuple((sanitize_terminal(line.text), line.style, line.kind) for line in session.snapshot_activity())
        if lines != self._lines:
            content = self.app.query_one("#content")
            follow = content.scroll_y >= content.max_scroll_y - 1
            transcript = Text()
            colors = {"wiz.err": "#DE8D86", "wiz.warn": "#E7A168", "wiz.ok": "#B6DDE5", "wiz.dim": "#7E7C88"}
            visible = []
            output = []
            def flush_output():
                if not output:
                    return
                if not self.output_expanded and len(output) > 4:
                    visible.append(("  Earlier output hidden. Ctrl+T expands it.", "wiz.dim", "output"))
                visible.extend(output if self.output_expanded else output[-4:])
                output.clear()
            for item in lines:
                if item[2] == "output":
                    # Keep output multiline so long stdout cannot defeat collapse.
                    output.extend((part, item[1], item[2]) for part in item[0].splitlines())
                else:
                    flush_output()
                    visible.append(item)
            flush_output()
            for line, style, kind in visible:
                if kind != "output":
                    line = line.lstrip("◈◆◇●◐✓✔✗✘✕✖→· ")
                transcript.append(line + "\n", style=colors.get(style, "#F3F1EC"))
            self.query_one("#run-flow", Static).update(transcript)
            self._lines = lines
            if follow:
                self.call_after_refresh(content.scroll_end, animate=False, immediate=True, x_axis=False)
        finished = bool(state.get("finished"))
        self._active = not finished
        self._now = sanitize_terminal("Finished · " + state["status"] if finished else state.get("now") or "Waiting for the next event").lstrip("\u25c8\u25c6\u25c7\u25cf\u25d0\u2713\u2714\u2717\u2718\u2715\u2716\u2192\u00b7 ")
        self._timer.pause() if finished else self._timer.resume()
        self._paint_activity()
        self.query_one("#result-actions").display = finished
        self.query_one("#result-diagram", Button).disabled = not state.get("investigation_id")
        return state

    def on_unmount(self):
        self._timer.stop()
