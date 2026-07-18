import uuid
from datetime import datetime, timezone
from wizard_kernel.contracts.request import InvestigationRequest
from wizard_kernel.contracts.status import LifecycleState
from wizard_kernel.session.investigation import Investigation


class InvestigationManager:
    def __init__(self) -> None:
        self._store: dict[str, Investigation] = {}

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
        return inv

    def get(self, inv_id: str) -> Investigation | None:
        return self._store.get(inv_id)

    def update(self, inv_id: str, **kwargs) -> None:
        inv = self._store[inv_id]
        for k, v in kwargs.items():
            setattr(inv, k, v)
        inv.updated_at = datetime.now(timezone.utc)

    def all(self) -> list[Investigation]:
        return list(self._store.values())
