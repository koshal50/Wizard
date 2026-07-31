"""Procedural pixel-art frames — soft Unicode blocks, no `#$%` noise.

Two animated pieces, each a pure function of a time value `t` (seconds). They
return Rich renderables (Text grids) so widgets can convert them to ANSI once
and hand them to prompt_toolkit.

    sunrise_frame(t)  -> the relaxing splash: a gold sun easing up over a
                         horizon strip, sky shifting indigo -> amber, a few
                         rays, settling into a gentle bob.

    ember_frame(t)    -> the "working" glyph: a small flame, deep-red outer
                         edge with an orange/yellow-white core, flickering
                         frame to frame.

Glyph vocabulary (soft, forms shapes): ▁▂▃▄▅▆▇█ ░▒▓ ● ◐ ◑ ─ ━. Never `#$%`.
"""

from __future__ import annotations

import math

from rich.text import Text

from wizard.cli.tui.theme import EMBER_RAMP, SKY_RAMP, SUN_RAMP, lerp_hex, ramp_at

# ---------------------------------------------------------------------------
# Sunrise splash
# ---------------------------------------------------------------------------

_SKY_W = 30
_SKY_H = 15
_HORIZON_ROW = _SKY_H - 2  # where the ground strip begins
_SUN_R = 6.0               # sun radius in *visual* units (see aspect note)
_SUN_TOP = 4.0             # resting sun-center row after it has risen

# Terminal cells are ~twice as tall as they are wide, so a circle drawn with
# equal row/col counts looks like a tall oval. We scale the vertical delta by
# _ASPECT (~2.0) when measuring distance, which makes the disc read as round.
_ASPECT = 2.05

# Public dimensions so widgets can size the left column to match.
SUN_WIDTH = _SKY_W
SUN_HEIGHT = _SKY_H

# Block density used to shade the sun body from rim (light) to nothing.
_SUN_FILL = "█"
_SKY_DOT = "·"  # faint star / sky speck


def _sun_center_y(t: float) -> float:
    """Sun vertical position: rises over ~3.5s, then bobs gently forever."""
    rise = 1.0 - math.exp(-t / 1.1)                       # 0 -> 1 ease-out
    settle = _HORIZON_ROW - rise * (_HORIZON_ROW - _SUN_TOP)
    bob = 0.18 * math.sin(t * 1.2)                        # subtle idle drift
    return settle + bob


def sunrise_frame(t: float) -> Text:
    """Build one frame of the sunrise animation at time `t` seconds."""
    cx = _SKY_W / 2.0
    cy = _sun_center_y(t)
    out = Text()

    for row in range(_SKY_H):
        # Sky gradient: top = deep indigo, horizon = warm amber. Brightens as
        # the sun climbs so the whole sky "wakes up".
        base = row / max(1, _HORIZON_ROW)
        warmth = (1.0 - cy / _HORIZON_ROW) * 0.35
        sky_col = ramp_at(SKY_RAMP, min(1.0, base + warmth))

        for col in range(_SKY_W):
            # Aspect-corrected distance -> round disc despite tall cells.
            dx = col - cx
            dy = (row - cy) * _ASPECT
            dist = math.sqrt(dx * dx + dy * dy)

            if row >= _HORIZON_ROW:
                # Ground strip: warm amber band, darker toward the bottom.
                gcol = lerp_hex("#e8843c", "#3d2168", (row - _HORIZON_ROW) / 2.0)
                out.append("━" if row == _HORIZON_ROW else "▔", style=gcol)
                continue

            if dist <= _SUN_R:
                # Sun body — bright core to cooler rim.
                sun_col = ramp_at(SUN_RAMP, dist / _SUN_R)
                out.append(_SUN_FILL, style=sun_col)
            elif dist <= _SUN_R + 1.6:
                # Soft glow halo just outside the disc.
                glow = lerp_hex("#ff8a2b", sky_col, (dist - _SUN_R) / 1.6)
                out.append("▒", style=glow)
            elif _is_ray(dx, dy, dist, t):
                out.append("─", style="#ffc94d")
            elif (col * 7 + row * 13) % 37 == 0 and row < _HORIZON_ROW - 3:
                # A few faint sky specks, only up high.
                out.append(_SKY_DOT, style=sky_col)
            else:
                out.append(" ", style=sky_col)
        if row != _SKY_H - 1:
            out.append("\n")
    return out


def _is_ray(dx: float, dy: float, dist: float, t: float) -> bool:
    """A handful of slowly-rotating rays radiating from the sun."""
    if dist < _SUN_R + 2.2 or dist > _SUN_R + 5.5:
        return False
    ang = math.atan2(dy, dx) + t * 0.15
    # 8 rays: highlight cells whose angle sits near a spoke.
    spoke = (ang % (math.pi / 4)) / (math.pi / 4)
    return spoke < 0.10 or spoke > 0.90


# ---------------------------------------------------------------------------
# Ember flame — the working indicator
# ---------------------------------------------------------------------------

# A compact flame silhouette, 5 rows tall. Each string is a row; characters map
# to ramp positions: outer edge -> inner core. Space = transparent.
#   .  faint outer   :  outer    o  mid    O  inner    @  core
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
    # Flicker: shift the whole ramp brighter/dimmer and jitter per-cell so the
    # flame breathes instead of sitting still.
    breath = 0.5 + 0.5 * math.sin(t * 6.0)
    out = Text()
    for r, line in enumerate(_FLAME_SHAPE):
        for c, ch in enumerate(line):
            if ch == " ":
                out.append(" ")
                continue
            pos = _SHAPE_TO_RAMP[ch]
            # Per-cell jitter keyed to position + time -> lively flicker.
            jitter = 0.12 * math.sin(t * 9.0 + r * 1.7 + c * 0.9)
            intensity = min(1.0, max(0.0, pos + jitter + 0.12 * breath))
            col = ramp_at(EMBER_RAMP, intensity)
            # Denser glyph toward the core, softer at the edges.
            glyph = "█" if intensity > 0.7 else "▓" if intensity > 0.4 else "▒"
            out.append(glyph, style=col)
        if r != len(_FLAME_SHAPE) - 1:
            out.append("\n")
    return out


def ember_inline(t: float) -> Text:
    """A single-cell pulsing ember for tight inline spots (spinner slot)."""
    intensity = 0.55 + 0.45 * math.sin(t * 6.0)
    col = ramp_at(EMBER_RAMP, intensity)
    glyph = "●" if intensity > 0.6 else "◐"
    return Text(glyph, style=col)
