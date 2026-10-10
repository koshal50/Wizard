"""InvestigationManager — session registry with disk-backed persistence.

Fix: state is now written to meta.json on create and on every terminal
state transition (completed / failed / cancelled). On startup, restore()
re-reads all meta.json files from disk so investigations survive restarts.

Multi-worker note: uvicorn must be started with --workers 1 (default dev
mode). Distributing across workers requires a shared process-external store
(Redis / DB) — out of scope for Phase 1-4. Documented in startup log.
"""
import logging
import uuid
from datetime import datetime, timezone

from wizard_kernel.contracts.request import InvestigationRequest
from wizard_kernel.contracts.status import LifecycleState, TERMINAL_STATES, is_terminal
from wizard_kernel.session.investigation import Investigation
from wizard_kernel.storage import fs_store

log = logging.getLogger(__name__)
MAX_MODEL_CALLS = 32

# States that signal an investigation is done — persist immediately on these
_TERMINAL_STATES = {
    LifecycleState.completed,
    LifecycleState.incomplete,
    LifecycleState.failed,
    LifecycleState.cancelled,
    LifecycleState.timed_out,
}


class InvestigationManager:
    def __init__(self) -> None:
        self._store: dict[str, Investigation] = {}
        self._lock = __import__("threading").Lock()
        self._runners: set[str] = set()

    def acquire_run(self, inv_id: str) -> bool:
        with self._lock:
            inv = self._store[inv_id]
            if inv_id in self._runners or is_terminal(inv.state):
                return False
            self._runners.add(inv_id)
            return True

    def release_run(self, inv_id: str) -> None:
        with self._lock:
            self._runners.discard(inv_id)

    def begin_step(self, inv_id: str, phase: LifecycleState, model: bool = False) -> dict:
        with self._lock:
            inv = self._store[inv_id]
            if is_terminal(inv.state):
                raise RuntimeError("Investigation is terminal")
            if inv.active_step and inv.active_step['status'] in {'queued', 'running'}:
                return {**inv.active_step, 'existing': True}
            if model and inv.model_calls >= MAX_MODEL_CALLS:
                raise RuntimeError("Model-call budget exhausted")
            inv.generation += 1
            inv.model_calls += int(model)
            inv.state = phase
            inv.active_step = {'id': f'{inv.id}:{phase.value}:{inv.generation}',
                               'phase': phase.value, 'status': 'running'}
            _persist(inv)
            return dict(inv.active_step)

    def end_step(self, inv_id: str, step_id: str, status: str) -> None:
        with self._lock:
            inv = self._store[inv_id]
            if inv.active_step and inv.active_step['id'] == step_id:
                if inv.active_step['status'] == 'running':
                    inv.active_step['status'] = status
                    _persist(inv)

    # ── Core API ──────────────────────────────────────────────────────────────

    def create(self, req: InvestigationRequest) -> Investigation:
        inv_id = f"inv_{uuid.uuid4().hex[:12]}"
        inv = Investigation(
            id=inv_id,
            repository_path=req.repository_path,
            intent=req.intent,
            targets=list(req.targets),
            options=req.options.model_dump(),
            question=req.question,
            budget_total=req.options.budget,
            budget_remaining=req.options.budget,
        )
        with self._lock:
            self._store[inv_id] = inv
            _persist(inv)   # write meta.json immediately on creation
        return inv

    def get(self, inv_id: str) -> Investigation | None:
        with self._lock:
            return self._store.get(inv_id)

    def update(self, inv_id: str, **kwargs) -> None:
        with self._lock:
            inv = self._store[inv_id]
            # Terminal states are absorbing: once an investigation has completed,
            # failed or been cancelled, no later writer may move it again.
            #
            # Without this, a cancel and the loop's own completion are a race whose
            # loser is silently overwritten — a client that cancels an investigation
            # that happens to be finishing is told "cancelled", then polls and is
            # told "completed". Whichever transition lands first is the answer.
            #
            # The refusal covers the whole update, not just the state: a caller
            # passing state + last_event wants the transition, so applying only the
            # last_event would leave a completed investigation recorded as
            # "cancelled by user".
            new_state = kwargs.get("state")
            if (inv.state in _TERMINAL_STATES
                    and new_state is not None
                    and new_state != inv.state):
                log.info("investigation %s is already %s; refusing transition to %s",
                         inv_id, inv.state, new_state)
                return
            for k, v in kwargs.items():
                setattr(inv, k, v)
            inv.updated_at = datetime.now(timezone.utc)
            # Persist only on terminal transitions — avoids excessive disk I/O
            if new_state in _TERMINAL_STATES:
                _persist(inv)

    def all(self) -> list[Investigation]:
        with self._lock:
            return list(self._store.values())

    # ── Startup restore ───────────────────────────────────────────────────────

    def restore(self) -> int:
        """Scan disk and reload all investigations into memory.
        Returns the number of investigations restored.
        Call once at startup before serving requests."""
        restored = 0
        inv_root = fs_store.data_root() / "investigations"
        if not inv_root.exists():
            return 0
        for inv_dir in inv_root.iterdir():
            if not inv_dir.is_dir():
                continue
            meta_path = inv_dir / "meta.json"
            if not meta_path.exists():
                continue
            try:
                import json
                data = json.loads(meta_path.read_text(encoding="utf-8"))
                inv = _from_dict(data)
                if not is_terminal(inv.state):
                    inv.state = LifecycleState.incomplete
                    inv.last_event = 'Runtime restarted before investigation finished'
                    inv.active_step = None
                    _persist(inv)
                    from wizard_kernel.control.report import generate
                    from wizard_kernel.control.investigation_graph import InvestigationGraph
                    fs_store.write_text(inv.id, 'verification_report.md', generate(inv, InvestigationGraph(inv.id), []))
                    inv.report_ready = True
                    _persist(inv)
                self._store[inv.id] = inv
                restored += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("could not restore %s: %s", inv_dir.name, exc)
        log.info("manager: restored %d investigations from disk", restored)
        return restored


# ── Helpers ───────────────────────────────────────────────────────────────────

def _persist(inv: Investigation) -> None:
    """Write investigation state to meta.json — survives process restart."""
    import dataclasses
    try:
        data = dataclasses.asdict(inv)
        fs_store.write(inv.id, "meta.json", data)
    except Exception as exc:  # noqa: BLE001
        log.warning("persist failed for %s: %s", inv.id, exc)


def _from_dict(data: dict) -> Investigation:
    """Reconstruct Investigation from persisted dict — handle datetime + enum fields."""
    from datetime import datetime
    for key in ("created_at", "updated_at", "started_at", "deadline_at", "finished_at"):
        if isinstance(data.get(key), str):
            data[key] = datetime.fromisoformat(data[key])
    if isinstance(data.get("state"), str):
        data["state"] = LifecycleState(data["state"])
    return Investigation(**data)

