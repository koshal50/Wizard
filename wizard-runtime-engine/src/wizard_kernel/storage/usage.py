"""Observational usage spool and persistence worker; no execution authority."""

# ruff: noqa: BLE001 -- optional telemetry must not change command outcomes
from __future__ import annotations

import json
import logging
import os
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from functools import lru_cache
from uuid import uuid4

from pydantic import AwareDatetime, BaseModel, Field

from wizard_kernel.storage import fs_store

log = logging.getLogger(__name__)
current_run: ContextVar[str | None] = ContextVar("usage_run", default=None)


class UsageEvent(BaseModel):
    event_id: str = Field(min_length=1, max_length=128)
    provider: str = Field(min_length=1, max_length=128)
    model: str = Field(min_length=1, max_length=256)
    agent: str | None = Field(default=None, max_length=128)
    provider_request_id: str | None = Field(default=None, max_length=256)
    input_tokens: int | None = Field(default=None, ge=0, le=2**63 - 1, strict=True)
    output_tokens: int | None = Field(default=None, ge=0, le=2**63 - 1, strict=True)
    total_tokens: int | None = Field(default=None, ge=0, le=2**63 - 1, strict=True)
    usage_source: str = Field(pattern="^(provider-reported|estimated|unavailable)$")
    accuracy: str = Field(pattern="^(exact|provisional|incomplete)$")
    created_at: AwareDatetime


class UsageStore:
    def __init__(self):
        self.root = fs_store.data_root() / "usage"
        self.root.mkdir(exist_ok=True)
        identity = self.root / "local_profile.json"
        if not identity.exists():
            # One runtime worker, same convention as InvestigationManager.
            self._write(identity, {"profile_id": uuid4().hex, "session_id": uuid4().hex})
        data = json.loads(identity.read_text("utf-8"))
        self.profile_id, self.session_id = data["profile_id"], data["session_id"]
        self.spool = self.root / "pending"
        self.spool.mkdir(exist_ok=True)
        self.lock = threading.RLock()
        self.start_lock = threading.Lock()
        self.runs: dict[str, dict] = {}
        self.database = None
        self.error: str | None = None
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.thread = None
        self.retry_at = 0.0
        self.lost = False
        self.started_at = datetime.now(UTC)
        self.recovery_pending = True

    @staticmethod
    def _write(path, value):
        tmp = path.with_name(path.name + "." + uuid4().hex + ".tmp")
        with tmp.open("w", encoding="utf-8") as stream:
            json.dump(value, stream)
            stream.flush()
            os.fsync(stream.fileno())
        tmp.replace(path)

    def start(self):
        with self.start_lock:
            self._start()

    def _start(self):
        if self.thread is not None:
            return
        if time.monotonic() < self.retry_at:
            return
        from wizard_kernel.storage.usage_db import database_url

        url = database_url()
        if not url:
            self.error = "PostgreSQL usage persistence is not configured"
            return
        try:
            from wizard_kernel.storage.usage_db import UsageDatabase

            self.database = UsageDatabase(url)
            self.flush()
            self.database.recover(self.profile_id, self.started_at)
            self.recovery_pending = False
            self.error = None
        except Exception as exc:
            self.error = (
                "PostgreSQL usage requires psycopg and psycopg_pool in the runtime Python environment"
                if isinstance(exc, ModuleNotFoundError)
                else "PostgreSQL usage configuration, schema, or connection unavailable"
            )
            log.warning(self.error)
            if self.database is None:
                self.retry_at = time.monotonic() + 2
                return
        self.thread = threading.Thread(target=self._worker, name="usage-persistence", daemon=True)
        self.thread.start()

    def close(self):
        self.stop.set()
        self.wake.set()
        if self.thread:
            self.thread.join(timeout=5)
        if self.database:
            self.database.close()

    def _worker(self):
        while not self.stop.is_set():
            self.flush()
            if self.recovery_pending and not any(self.spool.glob("*.json")):
                try:
                    self.database.recover(self.profile_id, self.started_at)
                    self.recovery_pending = False
                    self.error = None
                except Exception:
                    self.error = "Usage restart reconciliation is awaiting PostgreSQL"
            self.wake.wait(2)
            self.wake.clear()

    def flush(self):
        if not self.database:
            return
        for path in sorted(self.spool.glob("*.json")):
            try:
                job = json.loads(path.read_text("utf-8"))
                self.database.persist(job)
                path.unlink()
                self.error = None
            except Exception:
                # Exception text can contain database URLs, so log a safe message.
                message = "Usage persistence failed; durable records are awaiting retry"
                if self.error != message:
                    log.warning(message)
                self.error = message
                return

    def begin(self, inv, session_id=None):
        with self.lock:
            account_id = getattr(inv, "account_id", None)
            profile = "account:" + account_id if account_id else self.profile_id
            session = session_id or getattr(inv, "usage_session_id", None) or self.session_id
            # A supplied/reused session cannot move usage between permanent owners.
            if account_id and not (session_id is None and session.startswith("account-session:")):
                from hashlib import sha256
                session = "account-session:" + sha256((profile + ":" + session).encode()).hexdigest()
            self.runs[inv.id] = {
                "run_id": inv.id,
                "session_id": session,
                "profile_id": profile,
                "command": inv.intent,
                "status": "running",
                "started_at": inv.started_at.isoformat(),
                "finished_at": None,
                "revision": 0,
                "pending_requests": 0,
                "incomplete": False,
            }
            inv.usage_session_id = self.runs[inv.id]["session_id"]
            self._journal(inv.id)

    def state(self, inv):
        with self.lock:
            if inv.id not in self.runs:
                return
            from wizard_kernel.contracts.status import is_terminal

            self.runs[inv.id]["status"] = inv.state.value if is_terminal(inv.state) else "running"
            self.runs[inv.id]["finished_at"] = (
                inv.updated_at.isoformat() if is_terminal(inv.state) else None
            )
            self._journal(inv.id)

    def _journal(self, run_id, events=()):
        try:
            run = self.runs[run_id]
            run["revision"] = max(time.time_ns(), run["revision"] + 1)
            self._write(
                self.spool / f"{run['revision']}_{run_id}_{uuid4().hex}.json",
                {"run": dict(run), "events": list(events)},
            )
            self.wake.set()
        except Exception:
            self.lost = True
            self.runs[run_id]["incomplete"] = True
            log.error("Usage spool write failed; accounting is incomplete")

    @contextmanager
    def operation(self, inv):
        with self.lock:
            if inv.id not in self.runs:
                self.begin(inv)
            self.runs[inv.id]["pending_requests"] += 1
            self._journal(inv.id)
        token = current_run.set(inv.id)
        try:
            yield
        finally:
            current_run.reset(token)
            with self.lock:
                self.runs[inv.id]["pending_requests"] -= 1
                self.state(inv)

    def response(self, response):
        run_id = current_run.get()
        if not run_id:
            return
        with self.lock:
            try:
                body = response.json()
                raw = body.get("usage_events")
                if not isinstance(raw, list):
                    self.runs[run_id]["incomplete"] = True
                    self._journal(run_id)
                    return
                events = []
                for event in raw:
                    try:
                        events.append(UsageEvent.model_validate(event).model_dump(mode="json"))
                    except Exception:
                        self.runs[run_id]["incomplete"] = True
                self._journal(run_id, events)
            except Exception:
                self.runs[run_id]["incomplete"] = True
                self._journal(run_id)

    def provider_response(self, response, agent, model):
        """Feed the direct Runtime transport into the same metadata-only spool."""
        from types import SimpleNamespace
        try:
            body = response.json() if response is not None else {}
        except ValueError:
            body = {}
        usage = body.get("usage") or {} if isinstance(body, dict) else {}
        counts = {name: usage.get(key) for name, key in (
            ("input_tokens", "prompt_tokens"), ("output_tokens", "completion_tokens"), ("total_tokens", "total_tokens"))}
        counts = {k: v if type(v) is int and v >= 0 else None for k, v in counts.items()}
        event = {"event_id": uuid4().hex, "provider": "cerebras", "model": model, "agent": agent,
                 "provider_request_id": (response.headers.get("x-request-id") or response.headers.get("request-id")) if response is not None else None,
                 "created_at": datetime.now(UTC).isoformat(), **counts,
                 "usage_source": "provider-reported" if counts["total_tokens"] is not None else "unavailable",
                 "accuracy": "exact" if all(v is not None for v in counts.values()) else "incomplete"}
        self.response(SimpleNamespace(json=lambda: {"usage_events": [event]}))

    def incomplete(self):
        run_id = current_run.get()
        if run_id:
            with self.lock:
                self.runs[run_id]["incomplete"] = True
                self._journal(run_id)

    def health(self, run_id=None):
        pattern = f"*_{run_id}_*.json" if run_id else "*.json"
        return {
            "persistence_pending": any(self.spool.glob(pattern)),
            "persistence_error": self.error,
            "accounting_incomplete": self.lost,
        }


@lru_cache(maxsize=1)
def get_usage() -> UsageStore:
    return UsageStore()


def capture_response(response):
    if current_run.get():
        observe("response", response)


def observe(method, *args):
    """Usage failures never change command decisions or results."""
    try:
        return getattr(get_usage(), method)(*args)
    except Exception:
        log.error("Usage observation failed; accounting is incomplete")


@contextmanager
def operation(inv):
    try:
        store = get_usage()
        scope = store.operation(inv)
        scope.__enter__()
    except Exception:
        log.error("Usage operation setup failed; accounting is incomplete")
        yield
        return
    try:
        yield
    except Exception as exc:
        import httpx

        if isinstance(exc, httpx.TransportError):
            store.incomplete()
        raise
    finally:
        try:
            scope.__exit__(None, None, None)
        except Exception:
            store.lost = True
            log.error("Usage operation teardown failed; accounting is incomplete")
