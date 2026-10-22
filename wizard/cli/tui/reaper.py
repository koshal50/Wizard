"""Original small pixel character; no third-party artwork or browser dependency."""
from rich.text import Text

BACKGROUND = "#08080A"


def pixels():
    """Return one original resting pose, shared by terminal and SVG previews."""
    grid = [[None for _ in range(36)] for _ in range(44)]
    def rect(x, y, w, h, colour):
        for row in range(max(0, y), min(44, y + h)):
            for col in range(max(0, x), min(36, x + w)):
                grid[row][col] = colour
    def polygon(points, colour):
        for y in range(44):
            for x in range(36):
                inside = False
                previous = points[-1]
                for current in points:
                    ax, ay = previous
                    bx, by = current
                    if (ay > y + .5) != (by > y + .5) and x + .5 < (bx-ax)*(y+.5-ay)/(by-ay)+ax:
                        inside = not inside
                    previous = current
                if inside:
                    grid[y][x] = colour
    # A pointed oversized hood, weighted robe and visible folded fabric.
    polygon([(17, 5), (22, 9), (24, 17), (23, 23), (25, 30), (28, 39),
             (23, 41), (18, 39), (13, 42), (10, 40), (5, 41), (8, 31),
             (7, 25), (10, 20), (8, 17), (10, 10)], "#42394F")
    polygon([(17, 7), (21, 11), (22, 20), (20, 25), (24, 38), (20, 37),
             (14, 40), (11, 37), (7, 39), (11, 28), (9, 25), (12, 19), (10, 16), (12, 11)], "#211D2B")
    polygon([(17, 8), (19, 12), (20, 20), (17, 24), (14, 21), (10, 17), (12, 12)], "#100F17")
    polygon([(17, 8), (13, 12), (11, 16), (12, 19), (9, 17), (11, 11)], "#675376")
    # Small bone face inside a deep hood; violet eye sockets, not a smiley glyph.
    polygon([(13, 14), (18, 13), (20, 16), (19, 20), (17, 22), (14, 21), (12, 18)], "#C9C0CC")
    rect(13, 14, 4, 1, "#EEE6E5")
    rect(13, 16, 2, 2, "#4B365E")
    rect(17, 16, 2, 2, "#4B365E")
    rect(14, 16, 1, 1, "#C8A7FF")
    rect(18, 16, 1, 1, "#C8A7FF")
    rect(16, 18, 1, 1, "#57485F")
    rect(15, 20, 3, 1, "#76677E")
    polygon([(11, 23), (15, 25), (11, 36), (10, 37)], "#3D334A")
    polygon([(18, 23), (21, 31), (22, 37), (19, 35)], "#302738")
    rect(13, 25, 7, 1, "#6D5686")
    rect(16, 26, 2, 2, "#9B7EDE")
    polygon([(19, 23), (24, 25), (28, 22), (29, 25), (24, 28), (20, 26)], "#4D405B")
    # Long staff and crescent blade with an edge highlight and a darker spine.
    polygon([(30, 7), (32, 7), (29, 42), (27, 42)], "#51435E")
    polygon([(30, 7), (31, 7), (28, 41), (27, 41)], "#867093")
    polygon([(15, 7), (20, 3), (27, 1), (32, 2), (35, 7), (34, 11),
             (32, 7), (29, 5), (24, 5), (18, 7)], "#5B4580")
    polygon([(16, 7), (21, 4), (27, 2), (31, 3), (33, 5), (28, 4), (23, 5)], "#B89AEF")
    rect(26, 23, 3, 2, "#C9C0CC")
    rect(26, 23, 2, 1, "#EEE6E5")
    rect(7, 28, 3, 2, "#B5A6BB")
    return grid


def terminal_pose():
    """Two image rows per terminal cell; this is pixel art, not an emoji."""
    grid = pixels()
    result = Text()
    for y in range(0, len(grid), 2):
        for x in range(len(grid[0])):
            result.append("▀", style=f"{grid[y][x] or BACKGROUND} on {grid[y+1][x] or BACKGROUND}")
        if y + 2 < len(grid):
            result.append("\n")
    return result
