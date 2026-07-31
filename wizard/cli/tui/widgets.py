"""Rich renderables for the TUI, plus the Rich -> ANSI bridge.

The layout is a persistent two-pane split: the sun animation sits on the left,
the current screen's content on the right. No borders — spacing and color do the
framing so it reads calm and premium. prompt_toolkit stacks the real input box
underneath; these views never own keyboard input.

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

from wizard.cli.tui.art import SUN_WIDTH, ember_frame, sunrise_frame
from wizard.cli.tui.theme import WIZARD_THEME

# One console, reused. truecolor so the hex ramps land exactly; force_terminal
# so ANSI codes are emitted even though we're writing to a capture buffer.
_console = Console(
    theme=WIZARD_THEME,
    force_terminal=True,
    color_system="truecolor",
    width=80,
)

_BRAND = "✦ wizard"


def render_to_ansi(renderable: RenderableType, width: int) -> ANSI:
    """Render a Rich renderable at `width` columns into a prompt_toolkit ANSI."""
    _console.width = max(20, width)
    with _console.capture() as capture:
        _console.print(renderable, end="")
    return ANSI(capture.get())


# ---------------------------------------------------------------------------
# The two-pane frame: sun on the left, content on the right, no borders.
# ---------------------------------------------------------------------------

def frame(t: float, right: RenderableType) -> RenderableType:
    """Compose the persistent sun-left / content-right layout."""
    grid = Table.grid(padding=(0, 4), expand=True)
    grid.add_column(width=SUN_WIDTH + 1, justify="left")
    grid.add_column(justify="left", ratio=1)
    # A blank top line on both sides so the content floats a little.
    grid.add_row(Padding(sunrise_frame(t), (1, 0, 0, 1)), Padding(right, (2, 0, 0, 0)))
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
    gerund: str,
    status: str,
    running: bool,
    activity: list,
    tokens: int,
    cost: float,
    t: float,
) -> RenderableType:
    """Working narration: ember + gerund, flow log, and the grey meter."""
    # Header: small ember flame beside the current gerund / status.
    head = Table.grid(padding=(0, 2))
    head.add_column(justify="center")
    head.add_column(justify="left")
    if running:
        right = Group(
            Text(f"{gerund}…", style="wiz.gerund"),
            Text("the runtime is at work", style="wiz.dim"),
        )
        head.add_row(ember_frame(t), right)
    else:
        badge = "wiz.ok" if status == "completed" else "wiz.warn"
        head.add_row(
            Text("✦", style=badge),
            Group(Text("done", style=badge), Text(f"status · {status}", style="wiz.dim")),
        )

    log = Text()
    if not activity:
        log.append("…", style="wiz.dim")
    for line in activity:
        log.append(line.text, style=line.style)
        log.append("\n")

    return Group(
        Text("✦ investigating", style="wiz.ember"),
        Text(""),
        head,
        Text(""),
        Text("flow", style="wiz.dim"),
        log,
        Text(""),
        token_meter(tokens, cost),
    )


def token_meter(tokens: int, cost: float, mock: bool = True) -> RenderableType:
    """Dim grey usage strip: tokens · $cost · mock."""
    meter = Text()
    meter.append("tokens ", style="wiz.meter")
    meter.append(f"{tokens:,}", style="wiz.meter.val")
    meter.append("   ·   ", style="wiz.meter")
    meter.append(f"${cost:.4f}", style="wiz.meter.val")
    if mock:
        meter.append("   ·   mock usage", style="wiz.meter")
    return meter


def result_right(status: str, report_markdown: str) -> RenderableType:
    """Final report as markdown, badged by outcome — no border."""
    if status == "completed":
        badge = Text("✓ complete", style="wiz.ok")
    elif status == "engine_unavailable":
        badge = Text("✷ engine unavailable", style="wiz.err")
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
    else:
        content = Text("No report was produced.", style="wiz.dim")

    return Group(
        badge,
        Text(""),
        content,
        Text(""),
        Text("Esc for menu  ·  q to quit", style="wiz.hint"),
    )
