"""Rich renderables for the TUI, plus the Rich -> ANSI bridge.

The layout is a persistent two-pane split: the wizard banner sits on the left,
the current screen's content on the right. No borders — spacing and color do the
framing so it reads calm and premium. prompt_toolkit stacks the real input box
underneath; these views never own keyboard input.

The WORKING state renders a Claude-Code-style live activity log:
  ● Summoning the runtime…              (green dot = done)
  ● Consulting Explorer                 (green dot = done)
    └ Read 256 lines                    (dim sub-line)
  ○ Verifying dependencies…             (pulsing hollow dot = running)

  ✦ conjuring…
  conjuring… (12s · 1,280 tokens · esc to interrupt)

Each builder returns a Rich renderable; `render_to_ansi` rasterizes the composed
frame to an ANSI string for a `FormattedTextControl`.
"""

from __future__ import annotations

from rich.console import Console, Group, RenderableType
from rich.markdown import Markdown
from rich.padding import Padding
from rich.table import Table
from rich.text import Text

from prompt_toolkit.formatted_text import ANSI

import math
import os
import time

from wizard.cli.tui.events import BulletRow
from wizard.cli.tui.pixelart import load_pixel_grid, render_frame
from wizard.cli.tui.session import GERUNDS
from wizard.cli.tui.theme import EMBER_RAMP, WIZARD_THEME, ramp_at

# One console, reused. truecolor so the hex ramps land exactly; force_terminal
# so ANSI codes are emitted even though we're writing to a capture buffer.
_console = Console(
    theme=WIZARD_THEME,
    force_terminal=True,
    color_system="truecolor",
    width=80,
)

_BRAND = "✦ wizard"

# ---------------------------------------------------------------------------
# Wizard banner — load the GIF once, render_frame does the fire flickering
# ---------------------------------------------------------------------------

_BANNER_W = 40
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
    # Oscillate intensity between 0.3 and 1.0
    intensity = 0.65 + 0.35 * math.sin(t * 5.0)
    # Interpolate between dim violet and bright amber
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
    _console.width = max(20, width)
    with _console.capture() as capture:
        _console.print(renderable, end="")
    return ANSI(capture.get())


# ---------------------------------------------------------------------------
# The two-pane frame: wizard banner on the left, content on the right, no borders.
# ---------------------------------------------------------------------------

def frame(t: float, right: RenderableType) -> RenderableType:
    """Compose the persistent wizard-banner-left / content-right layout."""
    grid = Table.grid(padding=(0, 4), expand=True)
    grid.add_column(width=_BANNER_W + 1, justify="left")
    grid.add_column(justify="left", ratio=1)
    grid.add_row(Padding(render_frame(_ensure_grid()), (1, 0, 0, 1)), Padding(right, (2, 0, 0, 0)))
    return grid


# ---------------------------------------------------------------------------
# Right-pane content per state (borderless)
# ---------------------------------------------------------------------------

def splash_right() -> RenderableType:
    """The quiet greeting shown beside the rising sun."""
    return Group(
        Text(_BRAND, style="wiz.accent"),
        Text(""),
        Text("a calmer way to question a codebase", style="wiz.dim"),
        Text(""),
        Text("press any key to begin", style="wiz.hint"),
    )


def menu_right(
    level: str,
    options: list[str],
    selected: int,
    family: str | None,
) -> RenderableType:
    """Family or target selection list."""
    if level == "family":
        heading = Text("what shall we do?", style="wiz.title")
        sub = Text("↑ ↓ to move  ·  Enter to open", style="wiz.dim")
    else:
        heading = Text(f"{family}  ·  pick a target", style="wiz.title")
        sub = Text("↑ ↓ to move  ·  Enter to choose  ·  Esc to go back", style="wiz.dim")

    rows = Text()
    for i, opt in enumerate(options):
        if i == selected:
            rows.append("▸ ", style="wiz.cursor")
            rows.append(f" {opt} ", style="wiz.selected")
        else:
            rows.append("  ")
            rows.append(opt, style="wiz.unselected")
        rows.append("\n")

    return Group(Text(_BRAND, style="wiz.accent"), Text(""), heading, sub, Text(""), rows)


def intent_right(family: str, target: str | None) -> RenderableType:
    """Prompt shown above the intent input box."""
    label = family if not target else f"{family} {target}"
    return Group(
        Text(_BRAND, style="wiz.accent"),
        Text(""),
        Text("what's on your mind?", style="wiz.title"),
        Text(""),
        Text(f"about to run  ·  {label}", style="wiz.accent"),
        Text(""),
        Text("type an intent below, or leave it blank", style="wiz.dim"),
        Text("Enter to begin  ·  Esc to go back", style="wiz.hint"),
    )


def working_right(
    snap: dict,
    bullets: list[BulletRow],
    t: float,
) -> RenderableType:
    """Claude-Code-style working view: dot-lifecycle log + verb + counter."""
    running = snap.get("running", False)
    status = snap.get("status", "")
    gerund = snap.get("gerund", "conjuring")
    tokens = snap.get("tokens", 0)
    cost = snap.get("cost", 0.0)
    elapsed_start = snap.get("elapsed_start", t)
    cancelled = snap.get("cancelled", False)

    parts: list[RenderableType] = []

    # --- Activity log (dot lifecycle) ---
    log = Text()
    for bullet in bullets:
        # Dot
        if bullet.status == "running":
            dot = _pulsing_dot(t)
            log.append_text(dot)
        elif bullet.status == "done":
            log.append_text(_done_dot())
        else:  # error
            log.append_text(_error_dot())

        # Step name
        name_style = "wiz.flow" if bullet.status != "error" else "wiz.err"
        log.append(f" {bullet.step_name}\n", style=name_style)

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
        # Cycle verb every ~500ms
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
        # Show final status
        if status == "completed":
            final = Text("✦ done", style="wiz.ok")
        elif status == "engine_unavailable":
            final = Text("✦ engine unavailable", style="wiz.err")
        elif status == "cancelled":
            final = Text("✦ cancelled", style="wiz.warn")
        else:
            final = Text(f"✦ {status}", style="wiz.warn")

        parts.append(final)

        # Final counter
        elapsed = int(t - elapsed_start)
        meter = Text()
        meter.append(f"completed in {elapsed}s", style="wiz.meter")
        meter.append(" · ", style="wiz.meter")
        meter.append(f"{tokens:,} tokens", style="wiz.meter.val")
        meter.append(" · ", style="wiz.meter")
        meter.append(f"${cost:.4f}", style="wiz.meter.val")
        meter.append(" · mock usage", style="wiz.meter")
        parts.append(meter)

    return Group(*parts)


def result_right(status: str, report_markdown: str) -> RenderableType:
    """Final report as markdown, badged by outcome — no border."""
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

    return Group(
        badge,
        Text(""),
        content,
        Text(""),
        Text("Esc for menu  ·  q to quit", style="wiz.hint"),
    )
