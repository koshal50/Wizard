"""Browser plane HTTP surface — B4 (screencast WebSocket + co-drive input) + B6 host.

Two planes (architecture §1):
- narration -> the existing ``/events`` endpoint (discrete ``browser.*`` events).
- pixels    -> THIS ephemeral WebSocket. CDP screencast frames flow out; optional
               human take-over input flows in. Frames NEVER touch EventBus history.

The BrowserRuntime owns its own event-loop thread (Playwright is async, the kernel
loop is sync). This route runs on FastAPI's loop, so frames are marshalled across
threads: the runtime's ``on_frame`` callback (browser thread) hands each frame to
this loop via ``call_soon_threadsafe``; a drain task awaits and sends it. Sync
runtime calls are offloaded with ``asyncio.to_thread`` so the server loop never blocks.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from wizard_kernel.world.browser import get_runtime

log = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/investigations", tags=["browser"])

_LIVE_HTML = Path(__file__).parent / "static" / "browser.html"


@router.get("/{inv_id}/live", response_class=HTMLResponse)
def live_view(inv_id: str) -> HTMLResponse:
    """Serve the self-contained live-view page (B6). A VS Code webview loads the same page."""
    try:
        return HTMLResponse(_LIVE_HTML.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return HTMLResponse("<h1>live view unavailable</h1>", status_code=500)


@router.websocket("/{inv_id}/screencast")
async def screencast(ws: WebSocket, inv_id: str) -> None:
    await ws.accept()
    runtime = get_runtime(inv_id)
    if runtime is None:
        await ws.send_json({"type": "error", "message":
                            "no live browser for this investigation "
                            "(browser_enabled is false, or it is not running)"})
        await ws.close()
        return

    loop = asyncio.get_running_loop()
    frames: asyncio.Queue[str] = asyncio.Queue(maxsize=8)

    def on_frame(data: str) -> None:
        # Runs on the browser's loop thread — hop back to THIS loop.
        def _put() -> None:
            if frames.full():
                try:
                    frames.get_nowait()  # drop oldest — pixels are ephemeral
                except asyncio.QueueEmpty:
                    pass
            frames.put_nowait(data)
        loop.call_soon_threadsafe(_put)

    async def _pump() -> None:
        while True:
            data = await frames.get()
            try:
                await ws.send_json({"type": "frame", "data": data})
            except Exception:  # noqa: BLE001 — socket gone; finally will clean up
                return

    pump_task = asyncio.create_task(_pump())
    try:
        await asyncio.to_thread(runtime.start_screencast, on_frame)
        while True:
            msg = await ws.receive_json()
            # Inbound co-drive input (only sent when the viewer toggles "take over").
            if isinstance(msg, dict) and msg.get("kind") in ("mouse", "key"):
                await asyncio.to_thread(runtime.send_input, msg)
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001 — a socket error must never crash the server
        log.debug("screencast socket error for %s", inv_id, exc_info=True)
    finally:
        pump_task.cancel()
        try:
            await asyncio.to_thread(runtime.stop_screencast)
        except Exception:  # noqa: BLE001
            pass
