r"""Rich renderables for the TUI, plus the Rich -> ANSI bridge.

Layout matching Claude Code CLI startup screen:

    ╭── wizard v0.2.0 ─────────────────┬─────────────────────────╮
    │   Welcome back Koshal!            │ Recent activity         │
    │                                   │ investigate · auth …    │
    │       [wizard pixel art]          │ verify · runtime …      │
    │                                   │                         │
    │  v0.2.0 · API Usage · mock tokens │                         │
    │             ~\Wizard              │                         │
    ╰───────────────────────────────────┴─────────────────────────╯

    ╭────────────────────────────────────────────────────────────╮
    │  what shall we do?                                         │
    │  ↑ ↓ to move · Enter to open                              │
    │  ▸  investigate                                            │
    │     verify / report / explain                              │
    ╰────────────────────────────────────────────────────────────╯

    › [input prompt]

One bordered box at the bottom holds all states (command picker, target
picker, intent, working, result) — content swaps, box stays.
"""


from __future__ import annotations

from rich.box import ROUNDED
from rich.console import Console, Group, RenderableType
from rich.columns import Columns
from rich.markdown import Markdown
from rich.padding import Padding
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from prompt_toolkit.formatted_text import ANSI

import math
import os
import time

from wizard import __version__
from wizard.cli.tui.events import BulletRow
from wizard.cli.tui.history import load_recent
from wizard.cli.tui.pixelart import load_pixel_grid, render_frame
from wizard.cli.tui.session import GERUNDS
from wizard.cli.tui.theme import EMBER_RAMP, WIZARD_THEME, ramp_at

# One console, reused. truecolor so the hex ramps land exactly; force_terminal
# so ANSI codes are emitted even though we're writing to a capture buffer.
_console = Console(
    theme=WIZARD_THEME,
    force_terminal=True,
    color_system="truecolor",
    width=120,
)

# ---------------------------------------------------------------------------
# Identity — dynamically replaceable when auth is wired up
# ---------------------------------------------------------------------------

# TODO(auth): Replace with real authenticated identity from the website/auth
# system. For now, hardcoded to the project owner. When auth is built, this
# should read from a session/config file (e.g. ~/.wizard/session.json).
def get_username() -> str:
    """Return the display name for the welcome message.

    Currently returns a hardcoded name. Replace this function body
    with the real auth lookup when the identity system is built.
    """
    return "Koshal"


# ---------------------------------------------------------------------------
# Wizard banner — load the GIF once, render_frame does the fire flickering
# ---------------------------------------------------------------------------

_BANNER_W = 32
_IMAGE_PATH = os.path.join(os.path.dirname(__file__), "wizard_banner_preview.gif")
_wizard_grid: list | None = None


def _ensure_grid() -> list:
    global _wizard_grid
    if _wizard_grid is None:
        _wizard_grid = load_pixel_grid(_IMAGE_PATH, _BANNER_W)
    return _wizard_grid


# ---------------------------------------------------------------------------
# Pulsing dot for running bullets
# ---------------------------------------------------------------------------

def _pulsing_dot(t: float) -> Text:
    """A hollow dot ○ that pulses between dim and bright."""
    intensity = 0.65 + 0.35 * math.sin(t * 5.0)
    col = ramp_at(EMBER_RAMP, intensity)
    return Text("○", style=col)


def _done_dot() -> Text:
    """A solid green dot ● for completed steps."""
    return Text("●", style="wiz.ok")


def _error_dot() -> Text:
    """A solid red dot ● for failed steps."""
    return Text("●", style="wiz.err")


# ---------------------------------------------------------------------------
# Rich -> ANSI bridge
# ---------------------------------------------------------------------------

def render_to_ansi(renderable: RenderableType, width: int) -> ANSI:
    """Render a Rich renderable at `width` columns into a prompt_toolkit ANSI."""
    _console.width = max(40, width)
    with _console.capture() as capture:
        _console.print(renderable, end="")
    return ANSI(capture.get())


# ---------------------------------------------------------------------------
# TOP PANEL — wizard identity left, recent activity right (ROUNDED border)
# ---------------------------------------------------------------------------

def top_panel() -> RenderableType:
    """Build the Claude-Code-style top panel with wizard identity + recent activity."""
    username = get_username()
    recent = load_recent(3)

    # --- Left side: identity + mascot + footer ---
    left_parts: list[RenderableType] = []

    # Welcome line
    welcome = Text()
    welcome.append(f"Welcome back {username}!", style="wiz.welcome")
    left_parts.append(welcome)
    left_parts.append(Text(""))

    # Wizard mascot (pixel art, centered)
    mascot = render_frame(_ensure_grid())
    left_parts.append(mascot)

    left_parts.append(Text(""))

    # Footer metadata
    footer = Text(justify="center")
    footer.append(f"v{__version__}", style="wiz.footer")
    footer.append(" · ", style="wiz.footer")
    footer.append("API Usage", style="wiz.footer")
    footer.append(" · ", style="wiz.footer")
    footer.append("mock tokens", style="wiz.footer")
    left_parts.append(footer)

    cwd_line = Text(justify="center")
    cwd_line.append(f"~\\Wizard", style="wiz.footer")
    left_parts.append(cwd_line)

    left_content = Group(*left_parts)

    # --- Right side: recent activity ---
    right_parts: list[RenderableType] = []

    activity_header = Text("Recent activity", style="wiz.activity")
    right_parts.append(activity_header)
    right_parts.append(Text(""))

    if recent:
        for entry in recent:
            line = Text()
            line.append(entry.display_line(), style="wiz.activity.line")
            right_parts.append(line)
    else:
        right_parts.append(Text("No recent activity", style="wiz.dim"))

    right_content = Group(*right_parts)

    # --- Compose left+right into a split panel ---
    grid = Table.grid(padding=(0, 3), expand=True)
    grid.add_column(ratio=1, justify="center")
    grid.add_column(ratio=1, justify="left")
    grid.add_row(
        Padding(left_content, (1, 1)),
        Padding(right_content, (1, 1)),
    )

    # Title in the top border
    title = Text()
    title.append(f" wizard v{__version__} ", style="wiz.panel.title")

    return Panel(
        grid,
        title=title,
        title_align="left",
        box=ROUNDED,
        border_style="wiz.panel",
        expand=True,
        padding=(0, 1),
    )


# ---------------------------------------------------------------------------
# COMMAND BOX — single persistent bordered panel, content swaps by state
# ---------------------------------------------------------------------------

def command_box_menu(
    level: str,
    options: list[str],
    selected: int,
    family: str | None,
) -> RenderableType:
    """State A/B: command or target picker inside the command box."""
    parts: list[RenderableType] = []

    if level == "family":
        heading = Text("what shall we do?", style="wiz.title")
        sub = Text("↑ ↓ to move  ·  Enter to open", style="wiz.dim")
    else:
        heading = Text(f"{family}  ·  pick a target", style="wiz.title")
        sub = Text("↑ ↓ to move  ·  Enter to choose  ·  Esc to go back", style="wiz.dim")

    parts.append(heading)
    parts.append(sub)
    parts.append(Text(""))

    rows = Text()
    for i, opt in enumerate(options):
        if i == selected:
            rows.append("  ▸ ", style="wiz.cursor")
            rows.append(f" {opt} ", style="wiz.selected")
        else:
            rows.append("    ")
            rows.append(opt, style="wiz.unselected")
        rows.append("\n")

    parts.append(rows)

    return Panel(
        Group(*parts),
        box=ROUNDED,
        border_style="wiz.panel",
        expand=True,
        padding=(1, 2),
    )


def command_box_intent(family: str, target: str | None) -> RenderableType:
    """State C: intent input prompt inside the command box."""
    label = family if not target else f"{family} {target}"

    parts: list[RenderableType] = [
        Text("what's on your mind?", style="wiz.title"),
        Text(""),
        Text(f"about to run  ·  {label}", style="wiz.accent"),
        Text(""),
        Text("type an intent below, or leave it blank", style="wiz.dim"),
        Text("Enter to begin  ·  Esc to go back", style="wiz.hint"),
    ]

    return Panel(
        Group(*parts),
        box=ROUNDED,
        border_style="wiz.panel",
        expand=True,
        padding=(1, 2),
    )


def command_box_working(
    snap: dict,
    bullets: list[BulletRow],
    t: float,
) -> RenderableType:
    """State D: live working view inside the command box — dots + verb + counter."""
    running = snap.get("running", False)
    status = snap.get("status", "")
    tokens = snap.get("tokens", 0)
    cost = snap.get("cost", 0.0)
    elapsed_start = snap.get("elapsed_start", t)
    cancelled = snap.get("cancelled", False)

    parts: list[RenderableType] = []

    # --- Activity log (dot lifecycle) ---
    log = Text()
    for bullet in bullets:
        # Dot with blinking effect for running
        if bullet.status == "running":
            dot = _pulsing_dot(t)
            log.append_text(dot)
        elif bullet.status == "done":
            log.append_text(_done_dot())
        else:
            log.append_text(_error_dot())

        # Step name
        name_style = "wiz.flow" if bullet.status != "error" else "wiz.err"
        log.append(f" {bullet.step_name}", style=name_style)

        # Elapsed time for this step
        if bullet.ended_at and bullet.started_at:
            step_secs = int(bullet.ended_at - bullet.started_at)
            if step_secs > 0:
                log.append(f" ({step_secs}s)", style="wiz.meter")
        elif bullet.status == "running":
            live_secs = int(t - (bullet.started_at - (time.monotonic() - t - elapsed_start)) if bullet.started_at else 0)
            # Show ticking seconds for running bullet
            running_secs = max(0, int(time.monotonic() - bullet.started_at))
            log.append(f" ({running_secs}s)", style="wiz.gerund")

        log.append("\n")

        # Detail sub-line
        if bullet.detail:
            log.append("  └ ", style="wiz.dim")
            log.append(f"{bullet.detail}\n", style="wiz.dim")

    if log.plain:
        parts.append(log)
    else:
        parts.append(Text("…", style="wiz.dim"))

    parts.append(Text(""))

    # --- Rotating verb line (only while running) ---
    if running and not cancelled:
        verb_idx = int(t * 2.0) % len(GERUNDS)
        current_verb = GERUNDS[verb_idx]

        verb_line = Text()
        verb_line.append("✦ ", style="wiz.accent")
        verb_line.append(f"{current_verb}…", style="wiz.gerund")
        parts.append(verb_line)

        # Ticking counter line
        elapsed = int(t - elapsed_start)
        counter = Text()
        counter.append(f"{current_verb}… ", style="wiz.gerund")
        counter.append("(", style="wiz.meter")
        counter.append(f"{elapsed}s", style="wiz.meter.val")
        counter.append(" · ", style="wiz.meter")
        counter.append(f"{tokens:,} tokens", style="wiz.meter.val")
        counter.append(" · ", style="wiz.meter")
        counter.append("esc to interrupt", style="wiz.meter")
        counter.append(")", style="wiz.meter")
        parts.append(counter)
    elif not running:
        if status == "completed":
            final = Text("✦ done", style="wiz.ok")
        elif status == "engine_unavailable":
            final = Text("✦ engine unavailable", style="wiz.err")
        elif status == "cancelled":
            final = Text("✦ cancelled", style="wiz.warn")
        else:
            final = Text(f"✦ {status}", style="wiz.warn")
        parts.append(final)

        elapsed = int(t - elapsed_start)
        meter = Text()
        meter.append(f"completed in {elapsed}s", style="wiz.meter")
        meter.append(" · ", style="wiz.meter")
        meter.append(f"{tokens:,} tokens", style="wiz.meter.val")
        meter.append(" · ", style="wiz.meter")
        meter.append(f"${cost:.4f}", style="wiz.meter.val")
        meter.append(" · mock usage", style="wiz.meter")
        parts.append(meter)

    return Panel(
        Group(*parts),
        box=ROUNDED,
        border_style="wiz.panel",
        expand=True,
        padding=(1, 2),
    )


def command_box_result(status: str, report_markdown: str) -> RenderableType:
    """State E: final report inside the command box."""
    if status == "completed":
        badge = Text("✓ complete", style="wiz.ok")
    elif status == "engine_unavailable":
        badge = Text("✷ engine unavailable", style="wiz.err")
    elif status == "cancelled":
        badge = Text("✷ cancelled", style="wiz.warn")
    else:
        badge = Text(f"● {status}", style="wiz.warn")

    if report_markdown.strip():
        content: RenderableType = Markdown(report_markdown)
    elif status == "engine_unavailable":
        content = Text(
            "The Runtime Engine at 127.0.0.1:8080 didn't respond.\n"
            "Start wizard-runtime-engine and try again.",
            style="wiz.dim",
        )
    elif status == "cancelled":
        content = Text(
            "The investigation was cancelled before completion.",
            style="wiz.dim",
        )
    else:
        content = Text("No report was produced.", style="wiz.dim")

    parts = [
        badge,
        Text(""),
        content,
        Text(""),
        Text("Esc for menu  ·  q to quit", style="wiz.hint"),
    ]

    return Panel(
        Group(*parts),
        box=ROUNDED,
        border_style="wiz.panel",
        expand=True,
        padding=(1, 2),
    )
