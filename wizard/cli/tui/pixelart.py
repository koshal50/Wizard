"""
pixelart.py
Convert an image into a colorful terminal "pixel art" scene (Claude-Code style),
with animated flicker/sparkle effects for fire/glow regions.

Usage:
    python pixelart.py <image_path> [--width 60] [--animate] [--frames 30] [--delay 0.08]

Requires: pillow, rich
    pip install pillow rich
"""

import argparse
import random
import time
import sys
from PIL import Image
from rich.console import Console
from rich.text import Text

console = Console()

# Shade characters from darkest/densest to lightest -- gives texture/edges
SHADES = ["█", "▓", "▒", "░"]

# Cell aspect ratio correction: 1.0 for half-block rendering
CHAR_ASPECT = 1.0


def sample_bg_color(img):
    """Use the image corners to figure out the actual background color (handles off-white JPG bg)."""
    w, h = img.size
    corners = [img.getpixel((0, 0)), img.getpixel((w - 1, 0)),
               img.getpixel((0, h - 1)), img.getpixel((w - 1, h - 1))]
    r = sum(c[0] for c in corners) / 4
    g = sum(c[1] for c in corners) / 4
    b = sum(c[2] for c in corners) / 4
    return (r, g, b)


def color_distance(c1, c2):
    return ((c1[0] - c2[0]) ** 2 + (c1[1] - c2[1]) ** 2 + (c1[2] - c2[2]) ** 2) ** 0.5


def luminance(r, g, b):
    return 0.299 * r + 0.587 * g + 0.114 * b


def shade_for_luminance(lum):
    if lum < 60:
        return SHADES[0]
    elif lum < 120:
        return SHADES[1]
    elif lum < 180:
        return SHADES[2]
    else:
        return SHADES[3]


def is_fire_pixel(r, g, b):
    return r > 180 and g > 90 and b < 130 and r >= g >= b


def load_pixel_grid_hq(path, width, bg_tolerance=38, edge_soften=18):
    """
    High-fidelity loader:
    - Upsamples with LANCZOS for smooth downscale (keeps facial detail legible)
    - Uses corner-sampled background color + soft alpha falloff near edges,
      instead of a hard white cutoff (removes the harsh 'cutout' look and JPG halo)
    Returns a grid of either None (fully transparent) or (r, g, b, alpha 0-255)
    """
    img = Image.open(path).convert("RGB")
    bg = sample_bg_color(img)

    aspect = img.height / img.width
    height = max(1, int(width * aspect / CHAR_ASPECT))
    img = img.resize((width, height), Image.LANCZOS)

    grid = []
    for y in range(height):
        row = []
        for x in range(width):
            r, g, b = img.getpixel((x, y))
            dist = color_distance((r, g, b), bg)
            if dist < bg_tolerance:
                row.append(None)
            elif dist < bg_tolerance + edge_soften:
                # soft edge: partial pixel, blend factor by distance
                alpha = int(255 * (dist - bg_tolerance) / edge_soften)
                row.append((r, g, b, alpha))
            else:
                row.append((r, g, b, 255))
        grid.append(row)
    return grid


# Backwards-compatible name
def load_pixel_grid(path, width):
    return load_pixel_grid_hq(path, width)


def render_frame(grid, frame_num=0, sparkle_chance=0.0):
    """Render one frame of the grid as Rich Text using truecolor half-blocks for high resolution."""
    text = Text()
    height = len(grid)
    width = len(grid[0]) if height > 0 else 0
    for y in range(0, height, 2):
        row_top = grid[y]
        row_bottom = grid[y+1] if y + 1 < height else [None] * width
        
        for x in range(width):
            top = row_top[x]
            bottom = row_bottom[x]
            
            if top is None and bottom is None:
                text.append(" ")
            elif top is None and bottom is not None:
                br, bg, bb, _ = bottom
                b_hex = f"#{br:02x}{bg:02x}{bb:02x}"
                text.append("▄", style=b_hex)
            elif top is not None and bottom is None:
                tr, tg, tb, _ = top
                t_hex = f"#{tr:02x}{tg:02x}{tb:02x}"
                text.append("▀", style=t_hex)
            else:
                tr, tg, tb, _ = top
                br, bg, bb, _ = bottom
                t_hex = f"#{tr:02x}{tg:02x}{tb:02x}"
                b_hex = f"#{br:02x}{bg:02x}{bb:02x}"
                text.append("▀", style=f"{t_hex} on {b_hex}")
        text.append("\n")
    return text


def animate(grid, frames=30, delay=0.08):
    with console.screen():
        for i in range(frames):
            console.print(render_frame(grid, i), end="")
            time.sleep(delay)
            console.clear()


def static_render(grid):
    console.print(render_frame(grid))


class Ember:
    __slots__ = ("x", "y", "vy", "vx", "life", "max_life", "size")

    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.vy = random.uniform(-1.4, -0.6)
        self.vx = random.uniform(-0.4, 0.4)
        self.max_life = random.randint(14, 26)
        self.life = self.max_life
        self.size = random.uniform(1.5, 3.5)

    def step(self):
        self.x += self.vx
        self.y += self.vy
        self.vy *= 0.97
        self.life -= 1

    @property
    def alive(self):
        return self.life > 0


def find_fire_spawn_points(grid):
    points = []
    for y, row in enumerate(grid):
        for x, cell in enumerate(row):
            if cell is not None:
                r, g, b, a = cell
                if is_fire_pixel(r, g, b) and a > 180:
                    points.append((x, y))
    return points


def export_gif(grid, out_path, frames=30, delay_ms=80, cell_px=10, bg_rgb=(14, 12, 18)):
    """
    Render a rich animated GIF:
    - alpha-blended soft edges against a dark backdrop (no harsh cutout halo)
    - flickering flame with hue/brightness jitter
    - physically simulated rising embers spawned from the flame region
    - ambient twinkle sparkles in empty space
    """
    from PIL import ImageDraw
    import PIL.Image as PILImage

    h = len(grid)
    w = len(grid[0]) if h else 0
    img_w, img_h = w * cell_px, h * cell_px

    fire_points = find_fire_spawn_points(grid)
    embers = []
    twinkles = {}  # (x,y) -> remaining frames

    gif_frames = []
    for f in range(frames):
        # spawn new embers from random fire points each frame
        if fire_points and random.random() < 0.9:
            for _ in range(random.randint(1, 3)):
                sx, sy = random.choice(fire_points)
                embers.append(Ember(sx, sy))

        # step + cull embers
        for e in embers:
            e.step()
        embers = [e for e in embers if e.alive]

        # randomly add/remove twinkles in empty cells
        if random.random() < 0.6:
            ty = random.randint(0, h - 1)
            tx = random.randint(0, w - 1)
            if grid[ty][tx] is None:
                twinkles[(tx, ty)] = random.randint(4, 9)
        expired = [k for k, v in twinkles.items() if v <= 0]
        for k in expired:
            del twinkles[k]
        for k in list(twinkles.keys()):
            twinkles[k] -= 1

        canvas = PILImage.new("RGB", (img_w, img_h), bg_rgb)
        draw = ImageDraw.Draw(canvas)

        # base image
        for y, row in enumerate(grid):
            for x, cell in enumerate(row):
                if cell is None:
                    if (x, y) in twinkles:
                        b = 255 - int(255 * (twinkles[(x, y)] / 9))
                        c = (255, min(255, 200 + b // 3), 140)
                        cx = x * cell_px + cell_px // 2
                        cy = y * cell_px + cell_px // 2
                        draw.ellipse([cx - 1, cy - 1, cx + 1, cy + 1], fill=c)
                    continue

                r, g, b, a = cell
                if is_fire_pixel(r, g, b):
                    flicker = random.uniform(0.8, 1.3)
                    r2 = min(255, int(r * flicker))
                    g2 = min(255, int(g * random.uniform(0.85, 1.1)))
                    b2 = min(255, int(b * random.uniform(0.6, 1.0)))
                    color = (r2, g2, b2)
                else:
                    color = (r, g, b)

                if a < 255:
                    # alpha-blend soft edge against background
                    t = a / 255
                    color = tuple(int(color[i] * t + bg_rgb[i] * (1 - t)) for i in range(3))

                draw.rectangle(
                    [x * cell_px, y * cell_px, x * cell_px + cell_px - 1, y * cell_px + cell_px - 1],
                    fill=color,
                )

        # draw embers on top
        for e in embers:
            t = e.life / e.max_life
            c = (255, int(180 + 60 * t), int(60 * t))
            px, py = e.x * cell_px, e.y * cell_px
            r = e.size * t + 1
            draw.ellipse([px - r, py - r, px + r, py + r], fill=c)

        gif_frames.append(canvas)

    gif_frames[0].save(
        out_path, save_all=True, append_images=gif_frames[1:],
        duration=delay_ms, loop=0,
    )


def main():
    parser = argparse.ArgumentParser(description="Image to colorful terminal pixel art")
    parser.add_argument("image", help="Path to input image")
    parser.add_argument("--width", type=int, default=110, help="Output width in characters")
    parser.add_argument("--animate", action="store_true", help="Play looping animation")
    parser.add_argument("--frames", type=int, default=30, help="Number of animation frames")
    parser.add_argument("--delay", type=float, default=0.08, help="Delay between frames (s)")
    parser.add_argument("--gif", type=str, default=None, help="Export animated GIF to this path instead of playing in terminal")
    args = parser.parse_args()

    grid = load_pixel_grid(args.image, args.width)

    if args.gif:
        export_gif(grid, args.gif, frames=args.frames, delay_ms=int(args.delay * 1000))
        print(f"Saved animated preview to {args.gif}")
        return

    if args.animate:
        try:
            animate(grid, frames=args.frames, delay=args.delay)
        except KeyboardInterrupt:
            pass
    else:
        static_render(grid)


if __name__ == "__main__":
    main()
