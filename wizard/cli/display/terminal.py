"""One-shot rendering over the same command generators and event presentation."""

import threading
import time

from rich.live import Live
from rich.markdown import Markdown
from rich.text import Text

from wizard.cli.display.usage import counter
from wizard.cli.tui.session import TuiSession


class _TokenLine:
    """One usage line, including TTYs where Rich intentionally disables Live."""

    def __init__(self, console, meter):
        self.console, self.meter = console, meter
        self.live = (
            Live(meter, console=console, transient=True, refresh_per_second=4)
            if console.is_terminal and not console.is_dumb_terminal
            else None
        )
        self.fallback = console.is_terminal and console.is_dumb_terminal
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.thread = None
        self.previous = ""

    def __enter__(self):
        if self.live:
            self.live.__enter__()
        elif self.fallback:
            self.refresh()
            self.thread = threading.Thread(
                target=self._tick, name="token-line", daemon=True
            )
            self.thread.start()
        return self

    def _tick(self):
        while not self.stop.wait(0.25):
            self.refresh()

    def _clear(self):
        if self.previous:
            self.console.file.write("\r" + " " * len(self.previous) + "\r")
            self.console.file.flush()
            self.previous = ""

    def refresh(self):
        if self.live:
            self.live.refresh()
        elif self.fallback:
            with self.lock:
                text = self.meter.__rich__().copy()
                text.truncate(max(1, self.console.width - 1), overflow="ellipsis")
                current = text.plain
                if current != self.previous:
                    self.console.file.write(
                        "\r" + current + " " * max(0, len(self.previous) - len(current))
                    )
                    self.console.file.flush()
                    self.previous = current

    def print(self, text):
        with self.lock:
            if self.fallback:
                self._clear()
            self.console.print(text, markup=False)
            if self.fallback:
                self.refresh()

    def __exit__(self, exc_type, exc, traceback):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=1)
        if self.live:
            self.live.__exit__(exc_type, exc, traceback)
        elif self.fallback:
            with self.lock:
                self._clear()


def run_command(family, words, console):
    from wizard.cli.tui.services import ServiceSupervisor

    supervisor = ServiceSupervisor()
    session = TuiSession(family=family, target=None, intent_text=" ".join(words))

    class Meter:
        def __rich__(self):
            return Text(
                counter(
                    session.usage,
                    (session.ended_at or time.monotonic()) - session.started_at,
                )
            )

    try:
        report = supervisor.ensure_all()
        for line in report.lines():
            console.print(line, markup=False)
        if not report.kernel_ok:
            raise RuntimeError("Runtime Engine is unavailable")
        supervisor.apply_env()
        # Rich's live line cooperates with logs; pipes and CI get one final line.
        with _TokenLine(console, Meter()) as display:
            for event in session._get_event_generator():
                shown = session._lines_shown()
                session._consume(event)
                added = session._lines_shown() - shown
                activity = session.snapshot_activity(last=added) if added else []
                for line in activity:
                    display.print(
                        f"[{line.role}] {line.text}" if line.role else line.text
                    )
                if event.get("event_type") == "usage.updated":
                    display.refresh()
        if session.report_markdown:
            console.print(Markdown(session.report_markdown))
        from wizard.cli.display.architecture import offer_upload

        if offer_upload(session, console) is False:
            return 1
        return 0 if session.status == "completed" else 1
    except KeyboardInterrupt:
        session.cancel()
        return 130
    except Exception as exc:  # noqa: BLE001 -- match existing TUI failure presentation
        console.print(f"Command failed: {exc}", markup=False)
        return 1
    finally:
        console.print(
            counter(
                session.usage,
                (session.ended_at or time.monotonic()) - session.started_at,
            ),
            markup=False,
        )
        supervisor.stop()
