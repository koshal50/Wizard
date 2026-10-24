"""Cross-process request gate shared with the Planner's Node adapter via SQLite."""
from __future__ import annotations

import logging
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from contextlib import contextmanager

_LOG = logging.getLogger(__name__)
_DEFAULT_DB = Path.home() / ".wizard" / "cerebras-rate-gate.sqlite3"


class CerebrasRateGate:
    def __init__(self, database_path: str | None = None, interval_seconds: float | None = None) -> None:
        self._path = Path(database_path or os.environ.get("WIZARD_CEREBRAS_GATE_DB") or _DEFAULT_DB)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        # Match the existing Node gate's conservative 5-RPM default. An explicit
        # configured account limit may override the spacing; reservation logic
        # and shared SQLite state are unchanged.
        if interval_seconds is None:
            try:
                interval_seconds = float(os.environ.get("WIZARD_CEREBRAS_INTERVAL", "12"))
            except ValueError:
                interval_seconds = 12.0
        self._interval = max(0.0, interval_seconds)
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS provider_gate (provider TEXT PRIMARY KEY, next_allowed REAL NOT NULL)")

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self._path, timeout=30)
        try:
            db.execute("PRAGMA busy_timeout=30000")
            with db:
                yield db
        finally:
            db.close()

    def acquire(self, cancel_check=None, on_wait=None, deadline=None) -> None:
        while True:
            if deadline is not None and time.monotonic() >= deadline:
                raise InterruptedError('Provider capacity wait exceeded investigation deadline')
            if cancel_check:
                cancel_check()
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute("SELECT next_allowed FROM provider_gate WHERE provider='cerebras'").fetchone()
                now = time.time()
                next_allowed = row[0] if row else 0.0
                if next_allowed <= now:
                    db.execute(
                        "INSERT INTO provider_gate(provider,next_allowed) VALUES('cerebras',?) "
                        "ON CONFLICT(provider) DO UPDATE SET next_allowed=excluded.next_allowed",
                        (now + self._interval,),
                    )
                    wait = 0.0
                else:
                    wait = next_allowed - now
            if wait <= 0:
                return
            if on_wait:
                on_wait(wait)
            _LOG.info('{"event":"provider_rate_limit_wait","provider":"cerebras","wait_seconds":%.3f}', wait)
            if cancel_check or deadline is not None:
                until = time.monotonic() + wait
                while time.monotonic() < until:
                    if cancel_check:
                        cancel_check()
                    if deadline is not None and time.monotonic() >= deadline:
                        raise InterruptedError('Provider capacity wait exceeded investigation deadline')
                    time.sleep(min(0.25, max(0, until-time.monotonic())))
            else:
                time.sleep(wait)

    def defer(self, seconds: float) -> None:
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT next_allowed FROM provider_gate WHERE provider='cerebras'").fetchone()
            db.execute(
                "INSERT INTO provider_gate(provider,next_allowed) VALUES('cerebras',?) "
                "ON CONFLICT(provider) DO UPDATE SET next_allowed=MAX(provider_gate.next_allowed, excluded.next_allowed)",
                (max(row[0] if row else 0.0, time.time() + seconds),),
            )

    def observe_response(self, headers, *, limited=False) -> dict:
        """Keep the shared gate behind provider feedback, without retrying."""
        names = ("retry-after", "x-ratelimit-limit-requests", "x-ratelimit-remaining-requests",
                 "x-ratelimit-reset-requests", "x-ratelimit-limit-requests-minute",
                 "x-ratelimit-remaining-requests-minute", "x-ratelimit-reset-requests-minute",
                 "x-ratelimit-limit-tokens-minute", "x-ratelimit-remaining-tokens-minute",
                 "x-ratelimit-reset-tokens-minute", "x-ratelimit-remaining-requests-day",
                 "x-ratelimit-reset-requests-day")
        snapshot = {name: str(headers[name])[:100] for name in names if name in headers}
        # Reservation spaces send times; response spacing also protects against
        # variable transport latency bunching arrivals at the provider.
        delay = self._interval
        for name in ("x-ratelimit-limit-requests-minute", "x-ratelimit-limit-requests"):
            try:
                limit = float(headers.get(name, "0"))
                if limit > 0:
                    delay = max(delay, 60 / limit)
            except ValueError:
                pass
        exhausted = any(headers.get(name) == "0" for name in (
            "x-ratelimit-remaining-requests", "x-ratelimit-remaining-requests-minute",
            "x-ratelimit-remaining-tokens-minute", "x-ratelimit-remaining-requests-day"))
        if limited or exhausted:
            delay = max(delay, retry_after_seconds(headers))
        self.defer(delay)
        return {"headers": snapshot, "cooldown_seconds": delay}


def retry_after_seconds(headers) -> float:
    value = headers.get("retry-after")
    if value:
        try:
            return max(0.0, float(value))
        except ValueError:
            try:
                when = parsedate_to_datetime(value)
                return max(0.0, (when.replace(tzinfo=when.tzinfo or timezone.utc) - datetime.now(timezone.utc)).total_seconds())
            except (TypeError, ValueError, OverflowError):
                pass
    delays = []
    for name in ("x-ratelimit-reset-requests", "x-ratelimit-reset-tokens",
                 "x-ratelimit-reset-requests-minute", "x-ratelimit-reset-tokens-minute",
                 "x-ratelimit-reset-requests-day"):
        value = headers.get(name)
        if not value:
            continue
        try:
            number = float(value)
            delays.append(max(0.0, number - time.time() if number > 10_000_000 else number))
        except ValueError:
            match = re.fullmatch(r"([0-9.]+)\s*(ms|s|m)?", value.strip(), re.I)
            if match:
                amount = float(match.group(1))
                unit = (match.group(2) or "s").lower()
                delays.append(amount / 1000 if unit == "ms" else amount * (60 if unit == "m" else 1))
    return max(delays) if delays else 60.0
