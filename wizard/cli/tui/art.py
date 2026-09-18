r"""The wizard banner, drawn from `ascii-art.svg` — whole, at whatever density fits.

That file is not a picture of text — it is text. Six thousand four hundred
`<text>` elements sit on a fixed 4.8 x 8.0 grid, each carrying one character
and that character's own colour; that is how an image was converted to coloured
ASCII.

**Nothing is ever sampled, thrown away or averaged.** Every drawn cell of the
figure reaches the screen at every size. What changes with the space available
is how many source cells share one terminal cell — and terminal cells carry
sub-cell structure that a character does not, so a smaller drawing is a
*denser* one rather than a thinner one:

    full     1 source row  per terminal row    62 x 50
    half     2 source rows per terminal row    62 x 25   (▀ ▄ █, 2 colours a cell)
    braille  4 source rows per terminal row    31 x 13   (⠿, 8 cells a cell)

The trade is vertical: a terminal cell is twice as tall as it is wide whatever
is put in it, so packing two or four source rows into one shortens the figure
in proportion. That shortening is the point — it is the only way to make the
drawing smaller — but it is a compression and not a rescaling, and the figure
is therefore squatter at the two denser packings than at 1:1. There is no
packing that is both smaller and proportionally identical: matching the source
cell's own 4.8 x 8.0 pitch against a 1 x 2 terminal cell needs a 5 x 6 sub-grid,
which no character provides.

**Cropping** is the one removal, and it takes out nothing that was drawn. The
grid is mostly filler: 4755 of its 6432 cells are a pure black `.` laid down as
background. It is invisible on a dark terminal and only costs columns, so a cell
whose every channel is at or below `_BG_MAX` is read as empty and the grid is
built from what is left — the figure.
"""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from functools import lru_cache

from rich.text import Text

ART_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ascii-art.svg")

# A cell no brighter than this in every channel is the converter's background
# filler, not part of the drawing.
_BG_MAX = 14

# One character and the colour it was drawn in.
Cell = tuple[str, tuple[int, int, int]]
Row = list["Cell | None"]
Grid = list[Row]


def _rgb(value: str | None) -> "tuple[int, int, int] | None":
    """Parse `rgb(r,g,b)`; None when the attribute is not in that form."""
    if not value or not value.startswith("rgb("):
        return None
    try:
        red, green, blue = (int(part) for part in value[4:-1].split(","))
    except ValueError:
        return None
    return (red, green, blue)


def _pitch(coords: list[float]) -> float:
    """The grid's spacing: the smallest gap between neighbouring coordinates.

    Derived rather than hardcoded to the 4.8 x 8.0 this file happens to use, so
    a re-export at another scale still lands on a grid — and, unlike ranking the
    distinct coordinates, a gap left inside the art keeps its row instead of
    being closed up.
    """
    gaps = [b - a for a, b in zip(coords, coords[1:]) if b - a > 0.01]
    return min(gaps) if gaps else 1.0


@lru_cache(maxsize=1)
def _grid() -> Grid:
    """Parse the SVG into rows of cells, cropped to the drawn figure.

    Parsed once for the life of the process: it is a 388 KB document and the
    result never changes.
    """
    placed: list[tuple[float, float, str, tuple[int, int, int]]] = []
    for node in ET.parse(ART_PATH).getroot().iter():
        # Tags arrive namespaced (`{http://www.w3.org/2000/svg}text`).
        if node.tag.rsplit("}", 1)[-1] != "text":
            continue
        rgb = _rgb(node.get("fill"))
        if rgb is None or max(rgb) <= _BG_MAX:
            continue  # background filler
        try:
            x, y = float(node.get("x")), float(node.get("y"))
        except (TypeError, ValueError):
            continue
        placed.append((x, y, node.text or " ", rgb))

    if not placed:
        return []

    xs = sorted({x for x, _, _, _ in placed})
    ys = sorted({y for _, y, _, _ in placed})
    px, py = _pitch(xs), _pitch(ys)
    x0, y0 = xs[0], ys[0]

    grid: Grid = [[None] * (round((xs[-1] - x0) / px) + 1)
                  for _ in range(round((ys[-1] - y0) / py) + 1)]
    for x, y, ch, rgb in placed:
        grid[round((y - y0) / py)][round((x - x0) / px)] = (ch, rgb)
    return grid


# How many source rows share one terminal row, per density. Each is a packing a
# terminal cell genuinely supports, so a denser figure is a smaller one that has
# lost nothing rather than a thinner one.
_FULL, _HALF, _BRAILLE = 1, 2, 4

# Braille only doubles up sideways as well: 2 dots across by 4 down per cell.
_BRAILLE_DOTS = {
    (0, 0): 0x01, (0, 1): 0x02, (0, 2): 0x04, (1, 0): 0x08,
    (1, 1): 0x10, (1, 2): 0x20, (0, 3): 0x40, (1, 3): 0x80,
}

# Upper and lower half-block, and the full block when both rows are drawn. A
# cell with two different colours is a half-block with one as the glyph's colour
# and the other as its background — which is what makes this lossless for two
# rows, where a plain character cell would have to choose between them.
_HALF_GLYPH = {(True, True): "█", (True, False): "▀", (False, True): "▄"}


def _style(rgb: "tuple[int, int, int]") -> str:
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


def _brightest(cells: list) -> "tuple[int, int, int] | None":
    """The colour of the brightest drawn cell in a block, or None if none is.

    For braille, where a cell has one foreground colour and up to eight dots to
    spend it on. Brightest rather than the first or the most common: the figure
    is a lit drawing on a black ground, so the brightest cell in a block is the
    one carrying the drawing and the rest are its darker edges.
    """
    drawn = [c for c in cells if c is not None]
    if not drawn:
        return None
    return max((c[1] for c in drawn), key=lambda rgb: sum(rgb))


def _render_full(grid: Grid) -> Text:
    """One source cell per terminal cell, in the glyph's own colour."""
    text = Text()
    last = len(grid) - 1
    for r, row in enumerate(grid):
        for cell in row:
            text.append(" " if cell is None else cell[0],
                        style="" if cell is None else _style(cell[1]))
        if r != last:
            text.append("\n")
    return text


def _render_half(grid: Grid) -> Text:
    """Two source rows per terminal row, as half-blocks.

    Both rows survive: the upper one is the glyph's colour and the lower one is
    its background, so a cell showing `▀` in red over black is the file's own two
    cells, not a blend of them. Only the empty/solid cases collapse, and there
    is nothing to lose when they do.
    """
    text = Text()
    height = len(grid)
    width = len(grid[0]) if grid else 0
    for r in range(0, height, 2):
        for c in range(width):
            top = grid[r][c]
            bottom = grid[r + 1][c] if r + 1 < height else None
            glyph = _HALF_GLYPH.get((top is not None, bottom is not None))
            if glyph is None:
                text.append(" ")
                continue
            style = _style(top[1] if top is not None else bottom[1])
            if top is not None and bottom is not None:
                style += f" on {_style(bottom[1])}"
            text.append(glyph, style=style)
        if r + 2 < height:
            text.append("\n")
    return text


def _render_braille(grid: Grid) -> Text:
    """Four source rows and two source columns per terminal cell, as braille.

    The densest of the three and so the smallest: eight source cells to one
    terminal cell, which puts the whole 62 x 50 figure in 31 x 13. Every dot is
    one cell of the file, so nothing is sampled — the figure is not summarised,
    it is packed.

    One colour per cell, taken from the block's brightest drawn cell: a braille
    pattern has a single foreground colour and there is nowhere to put a second.
    """
    text = Text()
    height = len(grid)
    width = len(grid[0]) if grid else 0
    for r in range(0, height, 4):
        for c in range(0, width, 2):
            bits = 0
            block: list = []
            for (dx, dy), bit in _BRAILLE_DOTS.items():
                rr, cc = r + dy, c + dx
                cell = grid[rr][cc] if rr < height and cc < width else None
                block.append(cell)
                if cell is not None:
                    bits |= bit
            if not bits:
                text.append(" ")
                continue
            text.append(chr(0x2800 + bits), style=_style(_brightest(block)))
        if r + 4 < height:
            text.append("\n")
    return text


#: Densities, widest-and-least-packed first. Picked by the rows available.
_DENSITIES = (
    (_FULL, _render_full),
    (_HALF, _render_half),
    (_BRAILLE, _render_braille),
)


def _packed(cols_per_cell: int, rows_per_cell: int) -> tuple[int, int]:
    """(columns, rows) the figure occupies at one packing."""
    grid = _grid()
    if not grid:
        return (0, 0)
    width, height = len(grid[0]), len(grid)
    return (-(-width // cols_per_cell), -(-height // rows_per_cell))


def _packing(rows_per_cell: int) -> int:
    """How many source columns share a cell at this density."""
    return 2 if rows_per_cell == _BRAILLE else 1


def _density_for(max_rows: int, max_cols: int = 0) -> int:
    """The least-packed density that fits the space offered.

    Least-packed, not densest: a half-block cell carries two source rows and a
    braille cell carries eight, and the smaller drawing is only worth its
    smaller glyphs when there is no room for the larger one. Given the room, the
    figure is drawn at its own size.

    Both axes are checked because the packing changes both. A figure that fits
    the rows and overruns the columns is not shrunk by the renderer — it is
    wrapped, which shears it into two half-wizards, so a density has to earn its
    place on width as well as height. Zero means "no limit" on that axis.
    """
    for rows_per_cell, _ in _DENSITIES:
        cols, rows = _packed(_packing(rows_per_cell), rows_per_cell)
        if (max_rows <= 0 or rows <= max_rows) and (max_cols <= 0 or cols <= max_cols):
            return rows_per_cell
    return _BRAILLE


def _centred(text: Text, width: int) -> Text:
    """The figure shifted right by one margin, the same margin on every row.

    Not `Text(justify="center")` and not `rich.align.Align`: both centre each
    line against *its own* width after the renderer has trimmed its trailing
    whitespace, so the figure's own indentation is re-applied row by row and the
    wizard shears — measured shifts of 13, 15, 18 and 19 columns down one
    drawing. One margin computed once from the block cannot do that: every row
    moves by the same amount, so the drawing keeps its shape whatever the width.

    The trailing whitespace is dropped rather than kept because it is empty
    cells — nothing drawn — and keeping it only gives the renderer something to
    trim. Nothing that was drawn is on the right of the last glyph by definition.
    """
    lines = [line.rstrip() for line in text.plain.splitlines()]
    if not lines:
        return text
    margin = " " * max(0, (width - max(len(line) for line in lines)) // 2)
    out = Text()
    for i, line in enumerate(lines):
        if i:
            out.append("\n")
        out.append(margin + line)
    return out


def banner(max_rows: int = 0, max_cols: int = 0, width: int = 0) -> Text:
    """The whole figure, packed into at most `max_rows` rows by `max_cols` columns.

    `width` is the room the figure is centred in — the half of the panel it
    belongs to. Zero leaves it flush left, which is what the tests want when
    they are measuring the figure itself rather than looking at it.

    `max_rows=0` means "no limit" and draws it at the art's own size. Otherwise
    the densest packing that fits is chosen, and the figure is centred, because
    the panel it is drawn into is half the terminal and the art is narrower than
    that at every density: left to itself it sits against the left edge of the
    box with a hand's width of empty panel beside it. Justification is a property
    of the Text, so the padding is decided when the frame is rendered at its real
    width — which is the only moment it can be.

    Cached per density — it is a few hundred spans and the panel is rasterized
    on the first frame of the app.
    """
    drawn = _render_at(_density_for(max_rows, max_cols))
    return _centred(drawn, width) if width else drawn


@lru_cache(maxsize=len(_DENSITIES))
def _render_at(rows_per_cell: int) -> Text:
    """Render the figure at one density. Cached: the art never changes."""
    for rows, render in _DENSITIES:
        if rows == rows_per_cell:
            return render(_grid())
    raise ValueError(f"no such density: {rows_per_cell} rows per cell")


def banner_size(max_rows: int = 0, max_cols: int = 0) -> tuple[int, int]:
    """(columns, rows) of the figure as it will be drawn in that space.

    Read from the art and the density, so it cannot drift from what `banner()`
    returns — the two are asked the same question and answer it the same way.
    """
    rows_per_cell = _density_for(max_rows, max_cols)
    return _packed(_packing(rows_per_cell), rows_per_cell)


def _from_source() -> tuple[int, int]:
    """(columns, rows) of the figure at the SVG's own scale.

    The size the figure is *drawn* at, independent of the density it is shown
    at: 62 x 50, every cell of it. The tests compare the two, because "whole"
    and "smaller" are only compatible if the packing is checked against this.
    """
    grid = _grid()
    return (len(grid[0]) if grid else 0, len(grid))



