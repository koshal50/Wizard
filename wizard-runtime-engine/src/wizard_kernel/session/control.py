"""Bounded single-flight calls for the existing Runtime loop.

Only the loop thread can commit observations/graphs. An expired remote response
is discarded; an operation worker never receives authority to advance the loop.
"""
from datetime import datetime, timezone, timedelta
import queue
import threading
import time

from wizard_kernel.contracts.status import LifecycleState, is_terminal
from wizard_kernel.session.manager import MAX_MODEL_CALLS


class InvestigationStopped(Exception):
    pass


class DeadlineExceeded(InvestigationStopped):
    pass


class NoProgress(InvestigationStopped):
    pass


class RunControl:
    def __init__(self, inv, manager):
        self.inv, self.manager = inv, manager
        self.expires = time.monotonic() + max(0, (inv.deadline_at - datetime.now(timezone.utc)).total_seconds())
        # Leave bounded teardown/report time inside the five-minute session.
        self.operation_expires = self.expires - min(8, max(0, self.expires - time.monotonic()) * 0.03)
        self.operation_deadline_at = datetime.now(timezone.utc) + timedelta(seconds=max(0, self.operation_expires - time.monotonic()))

    def remaining(self):
        return max(0.0, min(self.expires - time.monotonic(),
                            (self.inv.deadline_at - datetime.now(timezone.utc)).total_seconds()))

    def check(self):
        if is_terminal(self.inv.state):
            raise InvestigationStopped(self.inv.last_event)
        if self.remaining() <= 0:
            raise DeadlineExceeded("Investigation timed out after 5 minutes")

    def call(self, phase, fn, *, model=False):
        self.check()
        if model and self.inv.model_calls >= MAX_MODEL_CALLS:
            raise NoProgress("Model-call budget exhausted; remaining work is unverified")
        step = self.manager.begin_step(self.inv.id, phase, model)
        if step.get('existing'):
            raise NoProgress('An orchestration step is already active; no second action was scheduled')
        result = queue.Queue(maxsize=1)
        def invoke():
            try:
                self.check()
                result.put((True, fn()))
            except BaseException as exc:
                result.put((False, exc))
        threading.Thread(target=invoke, daemon=True, name=step['id']).start()
        status = 'failed'
        try:
            while True:
                self.check()
                if time.monotonic() >= self.operation_expires:
                    raise DeadlineExceeded('Investigation reached its deadline; reserved time is used for cleanup and report')
                try:
                    ok, value = result.get(timeout=min(0.05, self.remaining()))
                except queue.Empty:
                    continue
                self.check()
                if not ok:
                    raise value
                status = 'completed'
                return value
        except InvestigationStopped:
            status = 'cancelled'
            raise
        finally:
            self.manager.end_step(self.inv.id, step['id'], status)


class ControlledPort:
    def __init__(self, port, control, phase):
        self.port, self.control, self.phase = port, control, phase

    def __getattr__(self, name):
        method = getattr(self.port, name)
        if not callable(method):
            return method
        def bounded(*args, **kwargs):
            self.control.check()
            if hasattr(self.port, 'deadline_at'):
                self.port.deadline_at = self.control.operation_deadline_at.isoformat()
            phase = self.phase
            if name in {'next_nodes', 'interpret'}:
                phase = LifecycleState.replanning
            return self.control.call(phase, lambda: method(*args, **kwargs), model=True)
        return bounded
