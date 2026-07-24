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
from wizard_kernel.contracts.status import LifecycleState
from wizard_kernel.session.investigation import Investigation
from wizard_kernel.storage import fs_store

log = logging.getLogger(__name__)

# States that signal an investigation is done — persist immediately on these
_TERMINAL_STATES = {LifecycleState.completed, LifecycleState.failed, LifecycleState.cancelled}


class InvestigationManager:
    def __init__(self) -> None:
        self._store: dict[str, Investigation] = {}

    # ── Core API ──────────────────────────────────────────────────────────────

    def create(self, req: InvestigationRequest) -> Investigation:
        inv_id = f"inv_{uuid.uuid4().hex[:12]}"
        inv = Investigation(
            id=inv_id,
            repository_path=req.repository_path,
            intent=req.intent,
            targets=list(req.targets),
            options=req.options.model_dump(),
            budget_total=req.options.budget,
            budget_remaining=req.options.budget,
        )
        self._store[inv_id] = inv
        _persist(inv)   # write meta.json immediately on creation
        return inv

    def get(self, inv_id: str) -> Investigation | None:
        return self._store.get(inv_id)

    def update(self, inv_id: str, **kwargs) -> None:
        inv = self._store[inv_id]
        for k, v in kwargs.items():
            setattr(inv, k, v)
        inv.updated_at = datetime.now(timezone.utc)
        # Persist only on terminal transitions — avoids excessive disk I/O
        new_state = kwargs.get("state")
        if new_state in _TERMINAL_STATES:
            _persist(inv)

    def all(self) -> list[Investigation]:
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
    for key in ("created_at", "updated_at"):
        if isinstance(data.get(key), str):
            data[key] = datetime.fromisoformat(data[key])
    if isinstance(data.get("state"), str):
        data["state"] = LifecycleState(data["state"])
    return Investigation(**data)

