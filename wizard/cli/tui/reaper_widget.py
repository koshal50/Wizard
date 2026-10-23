"""Native display of the user-requested reaper. Assets stay in the user's cache."""
from functools import lru_cache
from pathlib import Path
import os
import time

from PIL import Image
from platformdirs import user_cache_dir
from textual.containers import Vertical
from textual.widgets import Static

# Import/probe before Textual starts reading terminal input. The library owns
# protocol placement and clipping; do not inject image escape sequences ourselves.
try:
    from textual_image.widget import Image as AutoImage, SixelImage, TGPImage, HalfcellImage
    from textual_image.renderable import Image as AutoRenderable
    from textual_image.renderable.sixel import Image as SixelRenderable
    from textual_image.renderable.tgp import Image as TGPRenderable
except ImportError:
    AutoImage = None

SOURCE = "https://saasisdead.si/mascot/spritesheet.webp"
CACHE = Path(user_cache_dir("wizard")) / "reaper" / "spritesheet.webp"


def cache_artwork():
    """Explicit setup, never an implicit request from the render loop."""
    import httpx
    with httpx.stream("GET", SOURCE, timeout=15, follow_redirects=False) as response:
        response.raise_for_status()
        data = bytearray()
        for chunk in response.iter_bytes():
            data.extend(chunk)
            if len(data) > 2_000_000:
                raise ValueError("Unexpected reaper asset size")
    from io import BytesIO
    with Image.open(BytesIO(data)) as image:
        if image.size != (1536, 2288) or image.format != "WEBP":
            raise ValueError("Unexpected reaper sprite layout")
        image.verify()
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    temporary = CACHE.with_suffix(".tmp")
    temporary.write_bytes(data)
    temporary.replace(CACHE)
    return CACHE


@lru_cache(maxsize=1)
def load_frames():
    """Keep complete 192x208 frames. Never downsample artwork into text pixels."""
    frames = {}
    with Image.open(CACHE) as sheet:
        if sheet.size != (1536, 2288):
            raise ValueError("Unexpected reaper sprite layout")
        for row, count in ((0, 5), (2, 8), (3, 4)):
            for col in range(count):
                image = sheet.crop((col*192, row*208, (col+1)*192, (row+1)*208)).convert("RGBA")
                # Preserve the sprite's alpha; flattening onto RGB paints a
                # black rectangle even when the terminal uses another colour.
                frames[row, col] = image
    return frames


def image_renderer():
    if AutoImage is None:
        return None, "Install Wizard's optional tui dependencies for full images."
    mode = os.environ.get("WIZARD_REAPER_RENDERER", "auto")
    if mode == "sixel":
        return SixelImage, "Sixel image"
    if mode == "tgp":
        return TGPImage, "Terminal image"
    if mode == "halfcell":
        return HalfcellImage, "Text approximation (explicitly selected)"
    if mode != "auto":
        return None, "Unknown image mode. Use auto, sixel, tgp or halfcell."
    if AutoRenderable in (SixelRenderable, TGPRenderable):
        return AutoImage, "Full image"
    return HalfcellImage, "Limited graphics. Enable terminal images for full detail."


class ReaperGuide(Vertical):
    """One small guide; it receives UI state and cannot perform project actions."""
    DEFAULT_CSS = """
    ReaperGuide { width: 29; height: auto; align: right bottom; }
    ReaperGuide #speech { width: 100%; height: auto; border: round #584653;
        color: #D9E8EE; padding: 0 1; margin-bottom: 1; }
    ReaperGuide #real-reaper { width: 18; height: auto; max-height: 12; }
    ReaperGuide #render-note { height: auto; color: #A3B8C2; }
    ReaperGuide #art-credit { width: 100%; height: 1; text-align: right; color: #7D7887; }
    """

    def compose(self):
        yield Static("Choose a command.\nI'll explain what it does.", id="speech", markup=False)
        renderer, self._render_mode = image_renderer()
        self._image_view = renderer(id="real-reaper", on_error=lambda exc: Static("Image rendering failed. Check terminal support.", markup=False)) if renderer else None
        if self._image_view is not None:
            yield self._image_view
            if "Limited graphics" in self._render_mode or "approximation" in self._render_mode:
                yield Static(self._render_mode, id="render-note", markup=False)
        else:
            yield Static(self._render_mode, id="render-note", markup=False)
        yield Static("saasisdead.si", id="art-credit", markup=False)

    def on_mount(self):
        self._motion_enabled = True
        self._speech_text = None
        self._speech_count = 0
        self._phase = "arrive"
        self._since = time.monotonic()
        self._last_frame = None
        try:
            self._frames = load_frames()
        except (OSError, ValueError):
            self._frames = {}
            self.query_one("#speech", Static).update("Reaper artwork is unavailable. Run its explicit cache setup.")
        self._timer = self.set_interval(.12, self._advance)
        self._advance()
        if self._image_view is None or not self._frames:
            self._timer.pause()

    def rendering_status(self):
        """Safe local diagnostics: distinguish no asset, no image, and clipped UI."""
        image = self._image_view
        return {
            "mode": self._render_mode,
            "asset_cached": CACHE.is_file(),
            "frames_loaded": len(self._frames),
            "frame_size": list(next(iter(self._frames.values())).size) if self._frames else None,
            "image_widget": type(image).__name__ if image is not None else None,
            "region": {"width": image.region.width, "height": image.region.height} if image is not None else None,
        }

    def explain(self, message, *, immediate=False):
        if message == self._speech_text:
            return
        self._speech_text = message
        self.query_one("#speech", Static).tooltip = message
        self._speech_since = time.monotonic()
        self._speech_count = len(message) if immediate or not self._motion_enabled else min(3, len(message))
        self.query_one("#speech", Static).update(message[:self._speech_count])
        self.call_after_refresh(self.query_one("#speech").scroll_end, animate=False)
        if self._phase != "arrive":
            self._phase, self._since = "wave", time.monotonic()
        if self._motion_enabled:
            self._timer.resume()
        self._advance()

    def set_motion(self, active):
        self._motion_enabled = active
        if hasattr(self, "_timer"):
            self._timer.resume() if active and self._image_view is not None and self._frames else self._timer.pause()
            if not active and self._speech_text is not None:
                self._speech_count = len(self._speech_text)
                self.query_one("#speech", Static).update(self._speech_text)

    def _advance(self):
        if self._speech_text is not None and self._speech_count < len(self._speech_text):
            count = min(len(self._speech_text), max(3, int((time.monotonic() - self._speech_since) * 72)))
            if count != self._speech_count:
                self._speech_count = count
                self.query_one("#speech", Static).update(self._speech_text[:count])
                self.call_after_refresh(self.query_one("#speech").scroll_end, animate=False)
        if not self._frames or self._image_view is None:
            if self._speech_text is None or self._speech_count == len(self._speech_text):
                self._timer.pause()
            return
        elapsed = time.monotonic() - self._since
        if self._phase == "arrive":
            if elapsed < .72:
                key = 2, min(7, int(elapsed / .09))
                if self._last_frame != key:
                    self._image_view.image = self._frames[key]
                    self._last_frame = key
                return
            self._phase, self._since = "wave", time.monotonic()
            elapsed = 0
        if self._phase == "wave" and elapsed < .84:
            key = 3, min(3, int(elapsed/.21))
        else:
            self._phase = "idle"
            # The source idle sequence is intentionally slow; no full-screen refresh.
            key = 0, (0, 1, 2, 3, 4, 3, 2, 1)[int(elapsed/.7) % 8]
        if self._last_frame != key:
            self._image_view.image = self._frames[key]
            self._last_frame = key

    def on_unmount(self):
        if hasattr(self, "_timer"):
            self._timer.stop()


if __name__ == "__main__":
    cache_artwork()
    print("Requested reaper artwork cached locally. No assets were added to the repository.")
