"""TUI palette — the single source of color for the whole interface.

Clash-of-Clans-wizard schema: indigo/violet robes, gold/amber accents, and an
ember red -> orange -> yellow gradient for the "working" flame. The token meter
lives in dim grey so it never competes with the content.

Every named style used by the TUI is declared here. Widgets and art reference
these names (or the raw hex ramps) rather than scattering color literals across
the codebase.
"""

from __future__ import annotations

from rich.theme import Theme

# ---------------------------------------------------------------------------
# Raw color ramps (hex) — used by procedural art that interpolates/indexes.
# ---------------------------------------------------------------------------

# Sky: deep indigo night -> violet -> warm amber dawn. Ordered dark -> light.
SKY_RAMP = [
    "#1a1030",  # deep indigo
    "#2a1a4a",  # indigo
    "#3d2168",  # violet
    "#5b2d7a",  # magenta-violet
    "#8a3d6e",  # dusk rose
    "#c25a4a",  # ember horizon
    "#e8843c",  # amber
    "#f6b73c",  # gold dawn
]

# Sun body: hot core -> cooler rim. Ordered bright -> deep.
SUN_RAMP = [
    "#fff3c4",  # near-white core
    "#ffe08a",  # pale gold
    "#ffc94d",  # gold
    "#ffab3d",  # amber
    "#ff8a2b",  # orange
]

# Ember flame: outer red -> orange -> inner yellow-white. Ordered outer -> inner.
EMBER_RAMP = [
    "#7a1512",  # deep ember red
    "#c62f1c",  # red
    "#ef5a1f",  # red-orange
    "#ff8a2b",  # orange
    "#ffb347",  # amber
    "#ffe08a",  # yellow-white inner
]

# ---------------------------------------------------------------------------
# Named Rich styles — referenced by widgets via style="wiz.<name>".
# ---------------------------------------------------------------------------

WIZARD_THEME = Theme(
    {
        # Base identity
        "wiz.base": "#c9b8ff",           # soft violet text
        "wiz.dim": "#6b5b95",            # muted indigo for secondary text
        "wiz.title": "bold #d9a6ff",     # violet-magenta headings
        "wiz.accent": "bold #ffc94d",    # gold accents / highlights
        "wiz.gold": "#ffd76a",           # plain gold
        # Selection / menu
        "wiz.selected": "bold #1a1030 on #ffc94d",  # gold pill, dark text
        "wiz.unselected": "#9a8fd0",     # dim violet rows
        "wiz.cursor": "bold #ffc94d",    # the ▸ marker
        # Working / flame narration
        "wiz.ember": "bold #ef5a1f",     # ember red-orange
        "wiz.gerund": "italic #ffb347",  # the moving gerund word
        "wiz.flow": "#c9b8ff",           # flow narration lines
        # Status semantics
        "wiz.ok": "bold #7ee081",        # goal satisfied / node ok (soft green)
        "wiz.warn": "bold #ffb347",      # caution / uncertain
        "wiz.err": "bold #ff5f5f",       # failed node / engine down
        "wiz.evidence": "#66d9d0",       # claim admitted (teal)
        # Meter
        "wiz.meter": "#5a5a5a",          # dim grey — tokens · cost
        "wiz.meter.val": "#8a8a8a",      # slightly brighter grey for numbers
        # Frames / chrome
        "wiz.border": "#5b2d7a",         # violet panel borders
        "wiz.border.hot": "#ef5a1f",     # ember border while working
        "wiz.hint": "#6b5b95",           # keybinding hints at the footer
        # Panel borders (ROUNDED box glyphs)
        "wiz.panel": "#e8843c",           # amber panel border (warm, visible)
        "wiz.panel.title": "bold #ffc94d", # gold panel title text
        "wiz.welcome": "bold #c9b8ff",    # soft violet for welcome text
        "wiz.activity": "#e8843c",        # amber for "Recent activity" header
        "wiz.activity.line": "#9a8fd0",   # dim violet for activity entries
        "wiz.footer": "#6b5b95",          # dim for footer metadata line
    }
)


def lerp_hex(a: str, b: str, t: float) -> str:
    """Linearly interpolate between two #rrggbb colors. t in [0, 1]."""
    t = 0.0 if t < 0.0 else 1.0 if t > 1.0 else t
    ar, ag, ab = int(a[1:3], 16), int(a[3:5], 16), int(a[5:7], 16)
    br, bg, bb = int(b[1:3], 16), int(b[3:5], 16), int(b[5:7], 16)
    r = round(ar + (br - ar) * t)
    g = round(ag + (bg - ag) * t)
    bl = round(ab + (bb - ab) * t)
    return f"#{r:02x}{g:02x}{bl:02x}"


def ramp_at(ramp: list[str], t: float) -> str:
    """Sample a color ramp at position t in [0, 1] with smooth interpolation."""
    if t <= 0.0:
        return ramp[0]
    if t >= 1.0:
        return ramp[-1]
    scaled = t * (len(ramp) - 1)
    i = int(scaled)
    return lerp_hex(ramp[i], ramp[i + 1], scaled - i)
