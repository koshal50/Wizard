import threading
from fastapi import APIRouter, Depends, HTTPException
from wizard_kernel.contracts.report import ReportResponse
from wizard_kernel.contracts.request import InvestigationRequest
from wizard_kernel.contracts.status import LifecycleState
from wizard_kernel.session.manager import InvestigationManager
from wizard_kernel.api.deps import get_manager
from wizard_kernel.storage import fs_store
from wizard_kernel.ports.planner import get_planner
from wizard_kernel.control import loop as kernel_loop

router = APIRouter(prefix="/v1/investigations", tags=["investigations"])


@router.get("", summary="List all investigations")
def list_investigations(
    manager: InvestigationManager = Depends(get_manager),
):
    """Return a summary list of all investigations known to this process.

    Note: investigations from previous server runs are restored from disk at startup.
    Multi-worker deployments will only see their own in-process + disk state.
    """
    return [
        {
            "investigation_id": inv.id,
            "status": inv.state,
            "repository_path": inv.repository_path,
            "intent": inv.intent,
            "targets": inv.targets,
            "nodes_completed": inv.nodes_completed,
            "claims_count": inv.claims_count,
            "created_at": inv.created_at.isoformat(),
        }
        for inv in manager.all()
    ]


@router.post("", status_code=201)
def create_investigation(
    req: InvestigationRequest,
    manager: InvestigationManager = Depends(get_manager),
):
    inv = manager.create(req)
    # manager.create() persists meta.json — no duplicate write here
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


@router.get("/{inv_id}/report", response_model=ReportResponse)
def get_report(
    inv_id: str,
    manager: InvestigationManager = Depends(get_manager),
):
    """Return the verification report for a completed investigation.

    The report is generated once when the investigation reaches the `completed`
    state and is served directly from disk — immutable after generation.
    """
    inv = manager.get(inv_id)
    if not inv:
        raise HTTPException(404, detail=f"Investigation {inv_id!r} not found")
    if inv.state not in (LifecycleState.completed, LifecycleState.reporting):
        raise HTTPException(409, detail="Report not ready — investigation not yet complete")
    data = fs_store.read_text(inv.id, "verification_report.md")
    return ReportResponse(
        investigation_id=inv.id,
        report_markdown=data or "# Report pending",
        report_path=f".wizard/investigations/{inv.id}/verification_report.md",
    )


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


@router.get("/{inv_id}/events")
def get_events(
    inv_id: str,
    since_seq: int = 0,
    manager: InvestigationManager = Depends(get_manager),
):
    """Poll for recent investigation events."""
    from wizard_kernel.session import events as event_bus
    from datetime import datetime, timezone
    
    inv = manager.get(inv_id)
    if not inv:
        raise HTTPException(404, detail=f"Investigation {inv_id!r} not found")
        
    recent = event_bus.get_recent_events(since_seq, inv_id)
    return [
        {
            "seq": ev.seq,
            "event_type": ev.event_type,
            "investigation_id": ev.investigation_id,
            "payload": ev.payload,
            "timestamp": datetime.fromtimestamp(ev.timestamp, tz=timezone.utc).isoformat()
        }
        for ev in recent
    ]
