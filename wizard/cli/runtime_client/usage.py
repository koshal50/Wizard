"""Usage HTTP/SSE transport. The runtime owns all accounting and aggregation."""

from __future__ import annotations

import json
import os
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from urllib.parse import urlparse

import httpx

_usage_listener = ContextVar("tui_usage_listener", default=None)


@contextmanager
def listen_usage(callback):
    """Route the existing consumer's snapshots directly to its TUI session."""
    token = _usage_listener.set(callback)
    try:
        yield
    finally:
        _usage_listener.reset(token)


def usage_listener():
    return _usage_listener.get()


def status(run_id=None):
    from wizard.cli.runtime_client.account import account_headers
    from wizard.cli.runtime_client.client import base_url

    headers = account_headers()
    with httpx.Client(timeout=5) as client:
        deadline = time.monotonic() + 2
        while True:
            response = client.get(
                base_url().removesuffix("/investigations") + "/usage",
                params={"run_id": run_id} if run_id else None,
                headers=headers,
            )
            if response.status_code == 404 and run_id:
                # A run started under another account must not replace the
                # current account's persisted totals after an account switch.
                run_id = None
                continue
            if response.status_code != 503 or time.monotonic() >= deadline:
                break
            try:
                pending = "awaiting" in str(response.json().get("detail", "")).lower()
            except (ValueError, AttributeError):
                pending = False
            if not pending:
                break
            time.sleep(0.2)
        if response.is_error:
            try:
                detail = response.json().get("detail", "Usage request failed")
            except (ValueError, AttributeError):
                detail = "Usage request failed"
            raise RuntimeError(
                f"Usage unavailable (HTTP {response.status_code}): {detail}"
            )
        response.raise_for_status()
        return response.json()


def standalone_status():
    """Reuse the supervisor to start only the runtime when it is not running."""
    try:
        return status()
    except httpx.ConnectError:
        from wizard.cli.runtime_client.client import base_url

        if urlparse(base_url()).hostname not in ("localhost", "127.0.0.1", "::1"):
            raise
    from wizard.cli.tui.services import ServiceSupervisor, build_specs

    supervisor = ServiceSupervisor()
    kernel = next(spec for spec in build_specs() if spec.key == "kernel")
    previous = os.environ.get("WIZARD_ENGINE_URL")
    try:
        report = supervisor.ensure_all([kernel])
        if not report.kernel_ok:
            raise RuntimeError("Runtime Engine is unavailable")
        os.environ["WIZARD_ENGINE_URL"] = f"http://127.0.0.1:{kernel.port}"
        return status()
    finally:
        supervisor.stop()
        if previous is None:
            os.environ.pop("WIZARD_ENGINE_URL", None)
        else:
            os.environ["WIZARD_ENGINE_URL"] = previous


def parse_sse(lines):
    """Ignore heartbeat comments; support multiline data and reconnect IDs."""
    event, data, event_id = "message", [], None
    for line in lines:
        if not line:
            if data:
                yield event, event_id, json.loads("\n".join(data))
            event, data = "message", []
            continue
        if line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        value = value.removeprefix(" ")
        if field == "event":
            event = value
        elif field == "id":
            event_id = value
        elif field == "data":
            data.append(value)


class UsageStream:
    def __init__(self, url, run_id, on_update=None, headers=None):
        self.url, self.run_id = url, run_id
        self.stop = threading.Event()
        self.completed = threading.Event()
        self.lock = threading.Lock()
        self.close_lock = threading.Lock()
        self.closed = False
        self.latest = None
        self.confirmed = None
        self.last_id = None
        self.on_update = on_update
        self.headers = dict(headers or {})
        self.client = httpx.Client(timeout=httpx.Timeout(20, connect=2))
        self.thread = threading.Thread(target=self._read, name="usage-sse", daemon=True)
        self.thread.start()

    def publish(self, payload):
        if payload.get("run_id", self.run_id) != self.run_id:
            return
        if "total_tokens" in payload:
            self.confirmed = dict(payload)
        elif self.confirmed:
            # A delivery failure is not a replacement accounting snapshot.
            payload = {**self.confirmed, **payload}
        event = {
            "event_type": "usage.updated",
            "investigation_id": self.run_id,
            "payload": payload,
        }
        if self.on_update:
            self.on_update(event)
            return
        with self.lock:
            self.latest = event

    def drain(self):
        with self.lock:
            latest, self.latest = self.latest, None
        return [latest] if latest else []

    def _read(self):
        delay = 0.5
        while not self.stop.is_set():
            try:
                headers = {**self.headers, "Accept": "text/event-stream"}
                if self.last_id:
                    headers["Last-Event-ID"] = self.last_id
                with self.client.stream("GET", self.url, headers=headers) as response:
                    if response.status_code == 503:
                        response.read()
                        try:
                            detail = response.json().get("detail", "Usage unavailable")
                        except (ValueError, AttributeError):
                            detail = "Usage unavailable"
                        if "awaiting" in str(detail).lower():
                            self.publish({"usage_state": "pending"})
                        else:
                            self.publish(
                                {"incomplete": True, "persistence_error": str(detail)}
                            )
                        if self.stop.wait(delay):
                            return
                        delay = min(delay * 2, 8)
                        continue
                    response.raise_for_status()
                    for event, event_id, payload in parse_sse(response.iter_lines()):
                        if self.stop.is_set():
                            return
                        if event_id:
                            self.last_id = event_id
                        if event == "usage":
                            self.publish(payload)
                            delay = 0.5
                        elif event == "complete":
                            self.completed.set()
                            return
                        elif event == "unavailable":
                            self.publish(
                                {
                                    "transport_error": "Usage stream reconnecting",
                                }
                            )
                if self.stop.wait(delay):
                    return
            except (httpx.HTTPError, ValueError, RuntimeError):
                self.publish(
                    {
                        "transport_error": "Usage stream reconnecting",
                    }
                )
                if self.stop.wait(delay):
                    return
            delay = min(delay * 2, 8)

    def final(self):
        # Let the existing SSE connection announce final persistence, then make
        # one authoritative read instead of rapidly polling a finishing run.
        self.completed.wait(timeout=2)
        try:
            with httpx.Client(timeout=2) as client:
                response = client.get(
                    self.url.removesuffix("/stream"), headers=self.headers
                )
                response.raise_for_status()
                latest = response.json()
                if latest.get("pending_requests"):
                    latest["incomplete"] = True
                return latest
        except (httpx.HTTPError, ValueError):
            return {
                "incomplete": True,
                "persistence_error": "Final usage snapshot could not be retrieved",
            }

    def close(self):
        self.stop.set()
        with self.close_lock:
            if self.closed:
                return
            self.closed = True
        self.client.close()
        if self.thread is not threading.current_thread():
            self.thread.join(timeout=0.2)
