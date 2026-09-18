r"""Rich renderables for the TUI, plus the Rich -> ANSI bridge.

The layout is two bordered boxes stacked, with the real input box underneath:

    ╭─  wizard v0.2.0  ──────────────────────────────────────╮
    │          ✦ wizard            Recent activity           │
    │  a calmer way to question…   investigate — Sep 18      │
    │          [wizard art]        verify — runtime          │
    │       v0.2.0 · wizard                                  │
    │  ~/finalyear_project                                   │
    ╰────────────────────────────────────────────────────────╯
    ╭────────────────────────────────────────────────────────╮
    │  what shall we do?                                     │
    │    ▸  investigate                                      │
    ╰────────────────────────────────────────────────────────╯
    › [input prompt]

(The two halves of the top panel are columns of one grid, so there is no rule
drawn between them; the spacing above is the grid's own padding.)

One bordered box at the bottom holds every state — command picker, target
picker, intent, working, result. The content swaps; the box stays. The top
panel does not change at all while the app is open, so it is rendered once and
its Window is given a fixed height, which is what lets the box below it scroll
on its own.

Nothing here reports a number it did not measure. The top panel used to be
sourced from a hardcoded identity — a name, an "API Usage" figure and a mock
token count — none of which came from anywhere, and the working box carried a
rotating verb ("divining…", "scrying…") chosen off the wall clock. What is
shown instead is the repository the run will actually read, the version, the
last few runs this machine really made, and the Runtime's own narration.
"""

from __future__ import annotations

import math
import os
import time

from rich.box import ROUNDED
from rich.console import Console, Group, RenderableType
from rich.markdown import Markdown
from rich.padding import Padding
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from prompt_toolkit.formatted_text import ANSI

from wizard import __version__
from wizard.cli.tui.art import banner, banner_size
from wizard.cli.tui.history import load_recent
from wizard.cli.tui.session import LogLine
from wizard.cli.tui.theme import EMBER_RAMP, WIZARD_THEME, ramp_at

# One console, reused. truecolor so the art's own colours and the hex ramps land
# exactly; force_terminal so ANSI codes are emitted even though we're writing to
# a capture buffer; legacy_windows off so Rich draws the ROUNDED box's real
# corner glyphs (╭ ╮ ╰ ╯) instead of substituting ASCII for them, which is what
# it does by default on Windows and is the whole of the frame this layout is
# built from.
_console = Console(
    theme=WIZARD_THEME,
    force_terminal=True,
    legacy_windows=False,
    color_system="truecolor",
    width=80,
)

# How many past runs the top panel lists. Three is what fits the box beside the
# art without the panel growing past the art's own height.
_RECENT_SHOWN = 3

# The row budget handed to the art when asking what its smallest density is.
# Any value that forces the densest packing will do — the answer is the same
# figure — and it is named rather than written as a bare 1 so the call reads as
# the question it is.
_MIN_ART_ROWS = 1

# Rows held back from the panel for the command box and the input line under it.
# Sized to the shortest box worth reading — a heading, a few list rows and the
# border around them — so a run in progress always has somewhere to narrate.
_BOX_ROWS = 20

# Columns of the panel that are not the art: two borders, two of the panel's own
# padding, three of the grid's gap between the halves, and a column either side.
_ART_CHROME = 10

# How many of the Verifier's next steps the working pane lists before it just
# counts the rest.
_NEXT_SHOWN = 4

# How many recent evidence admissions the flow keeps. Evidence is one line per
# observation, so it is capped rather than listed; the steps behind it are the
# loop and are all kept, because the pane scrolls and dropping them would put
# them out of reach instead of out of the way.
_EVIDENCE_SHOWN = 3

# Width of the actor column on the left of each flow line. Sized to the longest
# role the narration emits ("explorer", "verifier"), so no name is ever cut and
# every line's text starts at the same offset. A role longer than this would
# push its own line out of alignment rather than be truncated — the column is a
# reading aid, and a mangled role is worse than a ragged one.
_ROLE_COLUMN = 8


# ---------------------------------------------------------------------------
# Ember flame — the working indicator beside the current step
# ---------------------------------------------------------------------------

_FLAME_SHAPE = [
    "  .o.  ",
    " .oOo. ",
    ".oO@Oo.",
    ".oO@Oo.",
    " :oOo: ",
]
_SHAPE_TO_RAMP = {".": 0.0, ":": 0.15, "o": 0.45, "O": 0.72, "@": 1.0}


def ember_frame(t: float) -> Text:
    """Build one frame of the flickering ember flame at time `t` seconds."""
    breath = 0.5 + 0.5 * math.sin(t * 6.0)
    out = Text()
    for r, line in enumerate(_FLAME_SHAPE):
        for c, ch in enumerate(line):
            if ch == " ":
                out.append(" ")
                continue
            pos = _SHAPE_TO_RAMP[ch]
            jitter = 0.12 * math.sin(t * 9.0 + r * 1.7 + c * 0.9)
            intensity = min(1.0, max(0.0, pos + jitter + 0.12 * breath))
            glyph = "█" if intensity > 0.7 else "▓" if intensity > 0.4 else "▒"
            out.append(glyph, style=ramp_at(EMBER_RAMP, intensity))
        if r != len(_FLAME_SHAPE) - 1:
            out.append("\n")
    return out


def render_to_ansi(renderable: RenderableType, width: int) -> ANSI:
    """Render a Rich renderable at `width` columns into a prompt_toolkit ANSI."""
    _console.width = max(20, width)
    with _console.capture() as capture:
        _console.print(renderable, end="")
    return ANSI(capture.get())


# ---------------------------------------------------------------------------
# The chrome: the top panel, and the one command box every state renders into
# ---------------------------------------------------------------------------

def _short_home(path: str) -> str:
    """`path` with the home directory folded to `~`, when it is under it.

    The panel is half the terminal wide and a Windows home directory is five
    levels of `C:\\Users\\<name>` before the interesting part starts. Folding it
    is what the shell does with the same path, and it leaves the two segments
    that identify the repository visible instead of letting them run off the
    edge of the box.
    """
    home = os.path.expanduser("~")
    if home and path.lower().startswith(home.lower()):
        return "~" + path[len(home):]
    return path


def art_cols(terminal_cols: int) -> int:
    """How many columns of the panel the wizard may have, for a terminal this wide.

    The panel is two equal halves, and the art sits in the left one. Everything
    that is not the art is fixed chrome: the panel's two borders, its padding,
    the gap the grid puts between the halves, and a column either side of the art
    itself. Counted here rather than measured at render time because the height
    of the panel has to be known before the first frame — a Window's height is
    fixed at construction — and the two have to be decided together: the art's
    packing changes its width as well as its height, so asking "how tall" without
    "how wide" picks a figure that does not fit.
    """
    return max(1, (terminal_cols - _ART_CHROME) // 2)


def art_rows(terminal_rows: int, available_cols: int = 0) -> int:
    """How many rows of the panel the wizard may have, for a terminal this tall.

    Everything but the art is fixed chrome, and the rows it is not allowed are
    the ones the command box and the input need: `_BOX_ROWS` of them, held back
    whether or not they are all used, because the box is where the run happens
    and a panel that takes the whole screen is a panel with nothing under it.
    Floored at the smallest density's height so a short terminal still gets a
    figure rather than a sliver, and capped at the art's own size so a very tall
    one does not get a floating wizard in an acre of panel.
    """
    _, smallest = banner_size(_MIN_ART_ROWS, available_cols)
    tallest = banner_size(0, available_cols)[1]
    return max(smallest, min(tallest, terminal_rows - _BOX_ROWS))


def _art_box(terminal_rows: int, terminal_cols: int) -> tuple[int, int]:
    """(rows, columns) the figure is actually drawn in, for this terminal.

    The height is read back off the packing rather than taken as the budget that
    chose it, which is what keeps the panel's fixed height equal to what the
    panel actually draws. Asking `banner_size` again with the answer can only
    return the same density — a denser one is shorter and would have been picked
    already, and a sparser one is taller and was rejected by the budget — so the
    two callers cannot disagree.
    """
    cols = art_cols(terminal_cols)
    return banner_size(art_rows(terminal_rows, cols), cols)[1], cols


def top_panel(repo_path: str = "", terminal_rows: int = 40,
              terminal_cols: int = 120) -> RenderableType:
    """The identity panel: what this is, what it will read, and what has run before.

    Left half is the wizard and the repository it will investigate; right half is
    the last few runs, read from the history file the session appends to when an
    investigation ends. Both halves are facts about this machine — there is no
    account to greet and nothing here is a placeholder standing in for one.

    Titled with the version and split with `Table.grid(expand=True)` at two equal
    ratios, so the two halves stay half the terminal however wide it is rather
    than drifting apart at one width and colliding at another.

    The art is drawn at the densest packing that fits `terminal_rows` — see
    `art.banner`. It is whole at every density, so a shorter terminal gets a
    smaller drawing that has lost nothing, not a cropped one.
    """
    # ── Left: the wizard, and which repository it is about to read ────────────
    # Elided to one line's worth. A Windows temp path is ninety columns and the
    # half-panel is fifty-five, so left alone it wraps — and the panel's height
    # is fixed by the art, so the wrapped half is clipped off the bottom rather
    # than accommodated. The tail is kept because the tail is the folder.
    repo_line = Text(justify="center")
    repo_line.append(_elide(_short_home(repo_path) if repo_path else os.getcwd(), 48),
                     style="wiz.footer")

    # The version, and nothing else. It was the version and the four command
    # names, which is 51 columns — one more than the half-panel has, so it
    # wrapped and put "explain" on a line of its own under the robe. The
    # commands are the menu directly below, spelled out in full; the panel does
    # not need to say them twice, and saying them once badly is worse than not
    # saying them at all.
    footer = Text(f"v{__version__} · wizard", style="wiz.footer", justify="center")

    art_h, art_w = _art_box(terminal_rows, terminal_cols)
    left = Group(
        Text("✦ wizard", style="wiz.welcome", justify="center"),
        Text("a calmer way to question a codebase", style="wiz.dim", justify="center"),
        Text(""),
        banner(art_h, art_w, art_w),
        footer,
        repo_line,
    )

    # ── Right: what has been run from here before ─────────────────────────────
    recent = load_recent(_RECENT_SHOWN)
    right_parts: list[RenderableType] = [Text("Recent activity", style="wiz.activity"), Text("")]
    if recent:
        for entry in recent:
            right_parts.append(Text(entry.display_line(), style="wiz.activity.line"))
    else:
        # Not an apology and not a fake row. An empty history is the ordinary
        # state of a project nobody has run the wizard in yet, and saying so is
        # the whole of what there is to say about it.
        right_parts.append(Text("nothing run from here yet", style="wiz.dim"))
    right = Group(*right_parts)

    grid = Table.grid(padding=(0, 3), expand=True)
    grid.add_column(ratio=1)
    grid.add_column(ratio=1)
    grid.add_row(Padding(left, (0, 1)), Padding(right, (0, 1)))

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


def top_panel_height(terminal_rows: int = 40, terminal_cols: int = 120) -> int:
    """Rows the panel occupies for a terminal this tall and wide.

    The panel is constant while the app runs, so its Window is given a fixed
    height and the box below it gets everything else — which is what lets that
    box scroll on its own instead of dragging the identity off the screen with
    it. Counted from the figure that is actually drawn and the fixed chrome
    rather than from the budget it was drawn under: on a tall terminal the
    budget is larger than any density needs, and reserving the budget would
    leave a band of blank panel under the wizard.

    Border (2), the two heading lines, a blank, the art, and the two footer
    lines. The right half is shorter than this at every history length the panel
    shows, so the art is the taller of the two and sets the height.
    """
    return _art_box(terminal_rows, terminal_cols)[0] + 7


def command_box(content: RenderableType) -> RenderableType:
    """The persistent bordered box the current screen renders inside.

    One box for every state, so the screen does not jump between a framed and an
    unframed layout as the user moves through it. Its height is its content's:
    Rich draws the bottom border after the last line, and the Window it sits in
    is the thing that scrolls when that is taller than the viewport.
    """
    return Panel(
        content,
        box=ROUNDED,
        border_style="wiz.panel",
        expand=True,
        padding=(1, 2),
    )


# ---------------------------------------------------------------------------
# Command-box content per state
# ---------------------------------------------------------------------------

def _elide(path: str, limit: int = 48) -> str:
    """Keep the end of a long path, which is the part that identifies it.

    The pane is around 50 columns and an absolute path is routinely longer than
    that, so the path would wrap and read as two unrelated lines. The tail —
    the folder the user named — is the half worth keeping.
    """
    if len(path) <= limit:
        return path
    return "…" + path[-(limit - 1):]


def _repo_line(repo_path: str) -> Text:
    """Which directory the run will read. Named, because it is not always cwd."""
    return Text(f"in  {_elide(repo_path)}", style="wiz.dim")


def menu_content(
    level: str,
    options: list[str],
    selected: int,
    family: str | None,
) -> RenderableType:
    """Family or target selection list — the commands, inside the box."""
    if level == "family":
        heading = Text("what shall we do?", style="wiz.title")
        sub = Text("↑ ↓ to move  ·  Enter to open", style="wiz.dim")
    else:
        heading = Text(f"{family}  ·  pick a target", style="wiz.title")
        sub = Text("↑ ↓ to move  ·  Enter to choose  ·  Esc to go back", style="wiz.dim")

    rows = Text()
    for i, opt in enumerate(options):
        if i == selected:
            rows.append("  ▸ ", style="wiz.cursor")
            rows.append(f" {opt} ", style="wiz.selected")
        else:
            rows.append("    ")
            rows.append(opt, style="wiz.unselected")
        rows.append("\n")

    return Group(heading, sub, Text(""), rows)


def intent_content(family: str, target: str | None, repo_path: str = "",
                   frontend_hint: str = "", has_frontend: bool = False) -> RenderableType:
    """Prompt shown above the intent input box."""
    label = family if not target else f"{family} {target}"
    parts: list[RenderableType] = [
        Text("what's on your mind?", style="wiz.title"),
        Text(""),
        Text(f"about to run  ·  {label}", style="wiz.accent"),
    ]
    if repo_path:
        parts.append(_repo_line(repo_path))
    # The one thing this screen has to say that the user cannot guess: a project
    # with a web client can be browsed, and the browser phase only happens if a
    # URL is named. Without this line the capability is invisible — the run
    # simply contains no browser steps, and nothing anywhere says why.
    if frontend_hint:
        parts.append(Text(""))
        parts.append(Text("◈ " + frontend_hint, style="wiz.hint"))
        if has_frontend:
            parts.append(Text("F2 to browse a different URL instead", style="wiz.dim"))
    parts.extend([
        Text(""),
        Text("type an intent below, or leave it blank", style="wiz.dim"),
        Text("Enter to begin  ·  Esc to go back", style="wiz.hint"),
    ])
    return Group(*parts)



def _short_path(path: str) -> str:
    """`path` relative to the working directory, when it is under it.

    The report is written to an absolute path, which is 70-odd columns and wraps
    the footer onto three rows. Relative to where the user launched it names the
    same file in a fraction of the space. A path outside the tree is left alone:
    a relative one would be a staircase of `..`.
    """
    try:
        rel = os.path.relpath(path, os.getcwd())
    except ValueError:      # a different drive on Windows has no relative form
        return path
    return path if rel.startswith("..") else rel


def _elapsed_line(snap: dict, t: float) -> RenderableType:
    """How long this has been going, and how to stop it. Both are measured."""
    started = snap.get("started_at") or t
    seconds = int(max(0.0, time.monotonic() - started))

    if snap.get("running"):
        line = Text()
        line.append(f"{seconds}s", style="wiz.meter.val")
        line.append("   ·   ", style="wiz.meter")
        line.append("esc to interrupt", style="wiz.meter")
        return line

    rows: list[RenderableType] = [Text(f"finished in {seconds}s", style="wiz.meter")]
    path = snap.get("report_path") or ""
    if path:
        rows.append(Text(_short_path(path), style="wiz.meter.val"))
    if snap.get("status") == "completed":
        rows.append(Text("Enter for the report", style="wiz.meter"))
    return Group(*rows)


def working_content(family: str, snap: dict, activity: list[LogLine], t: float) -> RenderableType:
    """Working narration: what the Runtime is doing now, and what it reported."""
    running = snap.get("running", False)
    status = snap.get("status", "")
    now = snap.get("now") or ""
    nexts = snap.get("nexts") or []

    # Head: the ember beside the current real step.
    head = Table.grid(padding=(0, 2))
    head.add_column(justify="center")
    head.add_column(justify="left")
    if running:
        head.add_row(
            ember_frame(t),
            Group(
                Text(now or "waiting for the runtime…", style="wiz.gerund"),
                Text("the runtime is at work", style="wiz.dim"),
            ),
        )
    else:
        badge = "wiz.ok" if status == "completed" else "wiz.warn"
        head.add_row(
            Text("✦", style=badge),
            Group(
                Text(status or "finished", style=badge),
                Text(now, style="wiz.dim") if now else Text(""),
            ),
        )

    # The flow: the loop the Runtime ran, oldest first.
    #
    # Evidence admissions are counted rather than listed. A run admits a claim
    # per observation, so on a real investigation they outnumber the steps that
    # produced them several times over, and a pane that shows them all is a wall
    # of "found evidence · EXECUTION → execute_command_exit_code" with the
    # narrative — which command ran, which goal closed, what the Verifier said —
    # scattered through it. The recent few are kept so the reader can still see
    # evidence arriving; the count says how many the pane is not showing, and
    # the report carries every one of them in full.
    steps = [ln for ln in activity if ln.kind != "evidence"]
    evidence = [ln for ln in activity if ln.kind == "evidence"]
    shown_evidence = evidence[-_EVIDENCE_SHOWN:]

    # Rebuild in order, so the flow still reads chronologically rather than as
    # two blocks.
    keep = set(map(id, steps)) | set(map(id, shown_evidence))
    visible = [ln for ln in activity if id(ln) in keep]

    log = Text()
    if not activity:
        log.append("…", style="wiz.dim")
    for line in visible:
        # The actor first, padded to a fixed column so the roles line up down
        # the pane and can be scanned on their own. A reader following the loop
        # wants to see the Explorer hand off to the Verifier and the Planner
        # step in when it has nothing — which is a question about the column,
        # and unanswerable when the name is buried mid-sentence at whatever
        # offset this line's tool name happens to end at.
        if line.role:
            log.append(f"{line.role:<{_ROLE_COLUMN}} ", style="wiz.role")
        log.append(line.text, style=line.style)
        log.append("\n")
    withheld = len(evidence) - len(shown_evidence)
    if withheld > 0:
        log.append(f"  + {withheld} more evidence lines · all of them in the report\n",
                   style="wiz.dim")

    parts: list[RenderableType] = [
        Text(f"✦ {family}", style="wiz.ember"),
        Text(""),
        head,
        Text(""),
        Text("flow", style="wiz.dim"),
        log,
    ]

    # What the Runtime's verifier said to look at next — its words, not ours.
    # A verifier that returns "needs_more_work" can name twenty-odd items, which
    # is more than the pane has rows; show the first few and say how many more
    # there were rather than letting the list push the flow off the screen.
    if nexts:
        parts.append(Text(""))
        parts.append(Text(f"next · {len(nexts)} from the verifier", style="wiz.dim"))
        nxt = Text()
        for item in nexts[:_NEXT_SHOWN]:
            nxt.append("  · ", style="wiz.dim")
            nxt.append(f"{item}\n", style="wiz.unselected")
        if len(nexts) > _NEXT_SHOWN:
            nxt.append(f"  + {len(nexts) - _NEXT_SHOWN} more\n", style="wiz.dim")
        parts.append(nxt)

    parts.append(Text(""))
    # Offered only once there is a page to look at. A key that promises a view
    # and opens an empty one teaches the reader to stop pressing it, and the
    # whole point of the page pane is that it is the one place the application
    # itself is visible.
    if isinstance(snap.get("page"), dict):
        parts.append(Text("b for the page", style="wiz.hint"))
    parts.append(_elapsed_line(snap, t))

    return Group(*parts)


# ---------------------------------------------------------------------------
# The live page — the browser's own account of where it is
# ---------------------------------------------------------------------------

# Width of the role column in the control list. Sized to the longest role the
# page's own control scan emits ("combobox"), so no role is ever cut and every
# name starts at the same offset — the point of the column is that a reader can
# scan it for the button they just watched get pressed.
_CONTROL_ROLE_COLUMN = 9

# The three things about a control a one-character column can say, in the order
# they matter. A control being pressed right now outranks one that cannot be
# pressed at all, which in turn outranks one that is merely off-screen: the
# reader is following the run, and the run's own step is the newest fact on the
# screen. Every one of these is read off the control, not inferred — the page
# reports `disabled` and `visible` itself.
_CONTROL_GLYPH = {"acted": "▸", "disabled": "✕", "hidden": "·"}


def _clip(text: str, limit: int) -> str:
    """`text` cut to `limit` columns, keeping its beginning.

    The head, not the tail as `_elide` keeps for paths: a path is identified by
    the folder at its end, and a control by the word at its start. "Sign in" cut
    to "Sign…" is still that button; cut from the front it is "…in", which is
    every button on the page.
    """
    if limit < 1:
        return ""
    if len(text) <= limit:
        return text
    if limit == 1:
        return "…"
    return text[: limit - 1] + "…"


def _control_line(control: dict, acted: bool, width: int) -> Text:
    """One control, as one line of the pane."""
    if acted:
        glyph = _CONTROL_GLYPH["acted"]
        style = "wiz.accent"
    elif control.get("disabled"):
        glyph, style = _CONTROL_GLYPH["disabled"], "wiz.dim"
    elif control.get("visible") is False:
        # Only `False`, never a missing key: a page that did not report
        # visibility has not told us the control is hidden, and guessing that it
        # is would mark a perfectly visible button on every page.
        glyph, style = _CONTROL_GLYPH["hidden"], "wiz.dim"
    else:
        glyph, style = " ", "wiz.unselected"

    role = str(control.get("role") or "")
    name = " ".join(str(control.get("name") or "").split())
    # A field is worth its contents — "the credentials actually landed" is the
    # finding a run that drives a form exists to get — so a value rides on the
    # control's own line rather than in a section of its own.
    value = control.get("value")
    if value:
        name = f"{name} = {value}"

    line = Text()
    line.append(f"{glyph} ")
    line.append(f"{_clip(role, _CONTROL_ROLE_COLUMN):<{_CONTROL_ROLE_COLUMN}} ", style="wiz.dim")
    line.append(_clip(name, width - _CONTROL_ROLE_COLUMN - 2), style=style)
    return line


def page_content(snap: dict, t: float, width: int) -> RenderableType:
    """The page the browser is on, as text — the app itself, in the pane.

    The other half of watching a run drive an application. The flow says what
    the wizard did; this says what it was looking at when it did it, which is
    the half a terminal cannot otherwise show — the screencast is pixels over a
    WebSocket, and a reader who wants to see the page a control belongs to has
    had nowhere to look but the browser window.

    It is the page's own account of itself, read by the same scan the planner
    writes its script from. Nothing here is drawn from the run's intentions: the
    controls are what the page contains, the values are what the fields hold,
    and the one marker is the selector the last action was addressed to. A page
    the run has not reached yet says so rather than showing an empty one, and a
    page that could not be read keeps the last reading and says how old it is —
    the two cases look identical on a blank pane and are not the same fact.

    Toggled rather than shown beside the flow, because at forty-odd columns
    neither would have room to be read. `b` flips between them.
    """
    page = snap.get("page")
    parts: list[RenderableType] = [Text("✦ live page", style="wiz.ember"), Text("")]

    if not isinstance(page, dict):
        parts.append(Text("the run has not reached a page yet.", style="wiz.dim"))
        if snap.get("running"):
            parts.append(Text("", style="wiz.dim"))
            parts.append(Text("it will appear here the moment the browser opens one.",
                              style="wiz.dim"))
        parts.append(Text(""))
        parts.append(_elapsed_line(snap, t))
        return Group(*parts)

    url = str(page.get("url") or "")
    title = " ".join(str(page.get("title") or "").split())
    controls = page.get("controls") or []

    parts.append(Text(_clip(url, width), style="wiz.accent"))
    if title:
        parts.append(Text(_clip(title, width), style="wiz.title"))
    parts.append(Text(""))
    parts.append(Text(f"{page.get('node_count', 0)} nodes · {len(controls)} controls",
                      style="wiz.dim"))
    parts.append(Text(""))

    act = snap.get("last_act") or {}
    acted_selector = act.get("selector")
    for control in controls:
        # Matched on the selector the action was addressed to, which is the
        # same string the page built for this control. A control the run has not
        # touched gets no marker; there is exactly one of these at a time, and
        # it is the step the reader is watching.
        acted = bool(acted_selector) and control.get("selector") == acted_selector
        parts.append(_control_line(control, acted, width))

    if not controls:
        parts.append(Text("  the page offers no controls", style="wiz.dim"))

    # What the run did to it, in the run's own words. Its own line rather than a
    # suffix on the marked control, because the sentence carries three facts the
    # marker column has no room for — which tool, which control by name, and
    # whether the page moved — and the last of those is the finding.
    if act:
        tool = str(act.get("tool") or "")
        verb = {"browser_click": "pressed", "browser_type": "typed"}.get(tool, tool or "acted on")
        parts.append(Text(""))
        line = Text("last · ", style="wiz.dim")
        # Clipped against the pane, not against a number chosen here. The
        # sentence is "last · <verb> <control> = <value> · page <effect>" and the
        # control is the one part of it with no bound of its own — a name can be
        # any length the page likes — so it is the part that yields when the line
        # would not fit, and the rest stays whole. What is left out is measured
        # rather than guessed, which is why it can be left out at all.
        # Not styled as a failure, because it is not one to this pane: whether an
        # inert control is a defect is a judgement about the application, and the
        # extractor files the same reading as a finding rather than a
        # contradiction for exactly this reason. The words say what was measured;
        # the reader decides what it means.
        suffix = f" · page {act['effect']}" if act.get("effect") else ""
        value = f" = {act['value']!r}" if act.get("value") is not None else ""
        target = act.get("name") or _control_name(controls, acted_selector)
        if not target:
            # Nothing on the page answers to that selector any more and the
            # runtime did not catch its name in time, so the selector is the only
            # thing left to call the control. Naming it — clipped, machine-shaped
            # and all — is still the point of this line; the alternative is a
            # sentence saying something was pressed and not what.
            target = _clip(str(acted_selector or ""),
                           max(8, width - len("last · ") - len(verb) - len(suffix) - 2))
        line.append(f"{verb} {target}", style="wiz.accent")
        if value:
            line.append(_clip(value, max(4, width - len(target) - len(verb) - 2)),
                        style="wiz.unselected")
        line.append(suffix, style="wiz.dim")
        parts.append(line)

    parts.append(Text(""))
    parts.append(Text("b for the flow", style="wiz.hint"))
    parts.append(_elapsed_line(snap, t))
    return Group(*parts)


def _control_name(controls: list, selector) -> str:
    """The readable name of the control a selector addressed, or "".

    Falls back to nothing rather than to the selector: `role=button[name="Sign
    in"]` is already shown above as `button  Sign in`, and repeating it here
    would put the machine's addressing of the control one line under the human's.
    Only used when the control is still on the page — after a click that
    navigates, the selector names something that is no longer there, and the
    selector itself is then the honest thing to show.
    """
    if not selector:
        return ""
    for control in controls:
        if control.get("selector") == selector:
            return " ".join(str(control.get("name") or "").split())
    return ""


def result_content(family: str, snap: dict, t: float) -> RenderableType:
    """Final report as markdown, badged by outcome — no border."""
    status = snap.get("status", "")
    report_markdown = snap.get("report_markdown", "")

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
            "The Runtime Engine did not answer, so nothing was investigated.\n"
            "The reason it gave is on the line below.",
            style="wiz.dim",
        )
    elif status == "cancelled":
        content = Text(
            "The investigation was cancelled before it produced a report.",
            style="wiz.dim",
        )
    else:
        content = Text("No report was produced.", style="wiz.dim")

    parts: list[RenderableType] = [badge, Text(""), content, Text("")]
    # On a failure the only useful thing on screen is the reason.
    if status != "completed":
        last = snap.get("now") or ""
        if last:
            parts.extend([Text("last · " + last, style="wiz.dim"), Text("")])
    parts.append(_elapsed_line(snap, t))
    parts.append(Text(""))
    if isinstance(snap.get("page"), dict):
        parts.append(Text("b for the page  ·  Esc for menu  ·  r to run another  ·  q to quit",
                          style="wiz.hint"))
    else:
        parts.append(Text("Esc for menu  ·  r to run another  ·  q to quit", style="wiz.hint"))

    return Group(*parts)
