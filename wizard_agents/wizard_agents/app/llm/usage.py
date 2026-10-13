"""Request-local, metadata-only provider accounting. No prompts or credentials."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from functools import wraps
from uuid import uuid4

_events: ContextVar[list[dict] | None] = ContextVar("provider_usage", default=None)


@contextmanager
def collect_usage() -> Iterator[list[dict]]:
    """Isolate concurrent service requests and retain failed-response usage."""
    events: list[dict] = []
    token = _events.set(events)
    try:
        yield events
    finally:
        _events.reset(token)


def _count(value: object) -> int | None:
    return value if type(value) is int and value >= 0 else None


def normalize_usage(payload: object) -> dict:
    """Missing or invalid metadata is unknown, never an exact zero estimate."""
    usage = payload.get("usage") if isinstance(payload, dict) else None
    usage = usage if isinstance(usage, dict) else {}
    input_tokens = _count(usage.get("prompt_tokens", usage.get("input_tokens")))
    output_tokens = _count(usage.get("completion_tokens", usage.get("output_tokens")))
    total_tokens = _count(usage.get("total_tokens"))
    if total_tokens is None and input_tokens is not None and output_tokens is not None:
        total_tokens = input_tokens + output_tokens
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "usage_source": "provider-reported"
        if total_tokens is not None
        else "unavailable",
        "accuracy": "exact"
        if all(v is not None for v in (input_tokens, output_tokens, total_tokens))
        else "incomplete",
    }


def record_usage(
    payload: object,
    *,
    provider: str,
    model: str,
    request_id: str | None = None,
    agent: str | None = None,
    event_id: str | None = None,
) -> None:
    events = _events.get()
    if events is None:
        return
    events.append(
        {
            "event_id": event_id or uuid4().hex,
            "provider": provider,
            "model": model,
            "agent": agent,
            "provider_request_id": request_id,
            "created_at": datetime.now(UTC).isoformat(),
            **normalize_usage(payload),
        }
    )


def usage_response(fn):
    """Attach metadata to existing runtime replies, including HTTP failures."""
    from fastapi import HTTPException
    from fastapi.responses import JSONResponse

    @wraps(fn)
    def wrapped(*args, **kwargs):
        packet = kwargs.get("packet") or (args[0] if args else {})
        enabled = isinstance(packet, dict) and packet.get("_usage") is True
        with collect_usage() as events:
            try:
                result = fn(*args, **kwargs)
            except HTTPException as exc:
                if not enabled:
                    raise
                return JSONResponse(
                    status_code=exc.status_code,
                    content={"detail": exc.detail, "usage_events": events},
                    headers=exc.headers,
                )
            except Exception:
                if not enabled:
                    raise
                return JSONResponse(
                    status_code=500,
                    content={
                        "detail": "Agent execution failed",
                        "usage_events": events,
                    },
                )
            return {**result, "usage_events": events} if enabled else result

    import inspect

    wrapped.__signature__ = inspect.signature(fn, eval_str=True)
    return wrapped
