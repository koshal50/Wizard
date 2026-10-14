"""Local-profile usage reports and persisted SSE snapshots, under existing v1 routes."""

# ruff: noqa: BLE001, B008 -- contain optional storage failures; standard FastAPI dependencies
import asyncio
import ipaddress
import json
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from wizard_kernel.storage import fs_store
from wizard_kernel.storage.usage import get_usage

router = APIRouter(prefix="/v1", tags=["usage"])


class Totals(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    llm_calls: int = 0
    incomplete: bool = False


class RunUsage(Totals):
    intent: str | None = None
    run_id: str
    session_id: str
    profile_id: str
    command: str
    status: str
    started_at: str
    finished_at: str | None = None
    revision: int
    pending_requests: int = 0
    persistence_pending: bool = False
    persistence_error: str | None = None
    accounting_incomplete: bool = False


class OverallUsage(BaseModel):
    scope: str
    profile_id: str
    session_id: str | None = None
    totals: Totals
    by_command: dict[str, Totals] = Field(default_factory=dict)
    current_run: RunUsage | None = None
    persistence_pending: bool = False
    persistence_error: str | None = None
    accounting_incomplete: bool = False


def local_usage(request: Request):
    # This MVP has no authentication. Never equate a caller-supplied session or
    # profile with ownership. Reports are local-only and use the runtime profile.
    try:
        local = request.client is not None and ipaddress.ip_address(request.client.host).is_loopback
    except ValueError:
        local = False
    if not local:
        raise HTTPException(403, "Usage is restricted to the single-user local runtime")
    try:
        store = get_usage()
    except Exception:
        raise HTTPException(503, "Local usage storage is unavailable") from None
    if store.database is None:
        # Optional persistence may have failed during runtime startup. Retry in
        # the existing store instead of making that failure permanent until exit.
        store.start()
    if store.database is None:
        raise HTTPException(503, store.error or "PostgreSQL usage persistence is unavailable")
    return store


def read_run(store, run_id):
    try:
        result = store.database.run(store.profile_id, run_id)
    except Exception:
        raise HTTPException(503, "PostgreSQL usage history is temporarily unavailable") from None
    if result is None:
        # Creation is asynchronous; pending spool entries are never exact history.
        if run_id in store.runs:
            raise HTTPException(503, "Run usage is awaiting PostgreSQL persistence")
        raise HTTPException(404, "Usage run not found in the local profile")
    return {**result, **store.health(run_id)}


@router.get("/investigations/{run_id}/usage", response_model=RunUsage)
def run_usage(run_id: str, store=Depends(local_usage)):
    return read_run(store, run_id)


@router.get("/usage", response_model=OverallUsage)
def overall_usage(
    session_id: str | None = None, run_id: str | None = None, store=Depends(local_usage)
):
    try:
        result = store.database.overall(store.profile_id, session_id)
        if run_id:
            result["current_run"] = read_run(store, run_id)
        if result.get("current_run"):
            run = result["current_run"]
            run.update(store.health(run["run_id"]))
            try:
                meta = fs_store.read(run["run_id"], "meta.json") or {}
                # Named targets supply the status intent; raw questions/prompts
                # and URLs (which may contain credentials) are never exposed.
                run["intent"] = (
                    ", ".join(
                        str(target)
                        for target in meta.get("targets", [])
                        if isinstance(target, str) and "://" not in target
                    )[:160]
                    or None
                )
            except (OSError, ValueError, TypeError, AttributeError):
                run["intent"] = None
        return {**result, **store.health()}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "PostgreSQL usage history is temporarily unavailable") from None


async def usage_stream(request, store, run_id, initial):
    """Snapshots replace totals; Last-Event-ID is advisory, never an additive delta."""
    snapshot = initial
    last = None
    heartbeat = time.monotonic()
    while not await request.is_disconnected():
        encoded = json.dumps(snapshot, sort_keys=True)
        if encoded != last:
            yield f"id: {snapshot['revision']}\nevent: usage\ndata: {encoded}\n\n"
            last = encoded
        if (
            snapshot.get("finished_at")
            and not snapshot.get("pending_requests")
            and not snapshot.get("persistence_pending")
        ):
            yield "event: complete\ndata: {}\n\n"
            return
        if time.monotonic() - heartbeat >= 15:
            yield ": heartbeat\n\n"
            heartbeat = time.monotonic()
        await asyncio.sleep(0.5)
        try:
            snapshot = await asyncio.to_thread(read_run, store, run_id)
        except HTTPException:
            yield 'event: unavailable\ndata: {"incomplete": true}\n\n'
            return


@router.get("/investigations/{run_id}/usage/stream")
async def stream_usage(run_id: str, request: Request, store=Depends(local_usage)):
    initial = await asyncio.to_thread(read_run, store, run_id)
    return StreamingResponse(
        usage_stream(request, store, run_id, initial),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
