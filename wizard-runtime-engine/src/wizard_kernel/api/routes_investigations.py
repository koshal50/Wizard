import threading
from fastapi import APIRouter, Depends, HTTPException
from wizard_kernel.contracts.request import InvestigationRequest
from wizard_kernel.contracts.status import LifecycleState
from wizard_kernel.session.manager import InvestigationManager
from wizard_kernel.api.deps import get_manager
from wizard_kernel.storage import fs_store
from wizard_kernel.ports.planner import get_planner
from wizard_kernel.control import loop as kernel_loop

router = APIRouter(prefix="/v1/investigations", tags=["investigations"])


@router.post("", status_code=201)
def create_investigation(
    req: InvestigationRequest,
    manager: InvestigationManager = Depends(get_manager),
):
    inv = manager.create(req)
    # manager.create() already persists meta.json via _persist() — no duplicate write here
    planner = get_planner(req.options.planner_url)
    t = threading.Thread(
        target=kernel_loop.run,
        args=(inv, manager, planner),
        daemon=True,
        name=f"loop-{inv.id}",
    )
    t.start()
    return {"investigation_id": inv.id, "status": inv.state}


@router.get("/{inv_id}")
def get_investigation(
    inv_id: str,
    manager: InvestigationManager = Depends(get_manager),
):
    inv = manager.get(inv_id)
    if not inv:
        raise HTTPException(404, detail=f"Investigation {inv_id!r} not found")
    return {
        "investigation_id": inv.id,
        "status": inv.state,
        "lifecycle": inv.state,
        "budget_remaining": inv.budget_remaining,
        "nodes_completed": inv.nodes_completed,
        "claims_count": inv.claims_count,
        "active_goals": inv.active_goals,
        "last_event": inv.last_event,
    }


@router.get("/{inv_id}/report")
def get_report(
    inv_id: str,
    manager: InvestigationManager = Depends(get_manager),
):
    inv = manager.get(inv_id)
    if not inv:
        raise HTTPException(404, detail=f"Investigation {inv_id!r} not found")
    if inv.state not in (LifecycleState.completed, LifecycleState.reporting):
        raise HTTPException(409, detail="Report not ready — investigation not yet complete")
    data = fs_store.read_text(inv.id, "verification_report.md")
    return {
        "investigation_id": inv.id,
        "report_markdown": data or "# Report pending",
        "report_path": f".wizard/investigations/{inv.id}/verification_report.md",
    }


@router.delete("/{inv_id}", status_code=200)
def cancel_investigation(
    inv_id: str,
    manager: InvestigationManager = Depends(get_manager),
):
    inv = manager.get(inv_id)
    if not inv:
        raise HTTPException(404, detail=f"Investigation {inv_id!r} not found")
    manager.update(inv_id, state=LifecycleState.cancelled, last_event="cancelled by user")
    return {"investigation_id": inv.id, "status": LifecycleState.cancelled}
