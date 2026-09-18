import threading
from fastapi import APIRouter, Depends, HTTPException
from wizard_kernel.contracts.report import ReportResponse
from wizard_kernel.contracts.request import InvestigationRequest
from wizard_kernel.contracts.status import LifecycleState, is_terminal
from wizard_kernel.session.manager import InvestigationManager
from wizard_kernel.api.deps import get_manager
from wizard_kernel.storage import fs_store
from wizard_kernel.ports.planner import get_planner
from wizard_kernel.control import loop as kernel_loop
from wizard_kernel.control.investigation_graph import get_graph
from wizard_kernel.world.sandbox import docker_status

# The tools that put a page on screen. A node that ran one of these and reached
# `complete` is proof the browser opened something, which is what separates "the
# agent never got to a page" from "the viewer arrived after the run ended".
_NAVIGATION_TOOLS = frozenset({"browser_navigate", "browser_back", "browser_click"})

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
    # Refuse a docker-mode request the machine cannot honour, HERE, rather than
    # letting the loop discover it: a container that cannot start fails inside
    # the sandbox, minutes in, as a raw docker error on an investigation that
    # already exists and has to be cleaned up. The user asked for isolation and
    # cannot get it — that is a request-time answer, and it names the fix.
    if req.options.sandbox_mode == "docker":
        usable, why = docker_status()
        if not usable:
            raise HTTPException(400, detail=(
                f"sandbox_mode='docker' was requested, but no Docker daemon is "
                f"reachable: {why}. Start Docker Desktop and retry, or drop the "
                f"docker mode to use the default local_dev sandbox."
            ))

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
        # Whether the run has stopped, answered by the owner of the lifecycle
        # rather than inferred by the caller. A client that keeps its own list of
        # terminal states drifts the moment one is added — the CLI's copy named
        # only completed/failed/cancelled, so it polled an `incomplete` run
        # forever and the TUI never showed a result.
        "is_terminal": is_terminal(inv.state),
        "budget_remaining": inv.budget_remaining,
        "nodes_completed": inv.nodes_completed,
        "claims_count": inv.claims_count,
        "active_goals": inv.active_goals,
        "last_event": inv.last_event,
    }


@router.get("/{inv_id}/frontier")
def get_frontier(
    inv_id: str,
    manager: InvestigationManager = Depends(get_manager),
):
    """What the investigation is doing now, and what it will do next.

    The live browser page reads this to fill its overlay, so it answers in the
    viewer's terms — the node in flight and the nodes still waiting — rather than
    making the page reconstruct a plan from the event stream.

    While the run is live this reads the in-process graph the loop registered. Once
    it has finished the registry still holds it (the graph is never unregistered),
    so a late viewer sees the final shape: `now` is null and `next` is empty.

    "next" is emptied on a terminal run rather than left as whatever the graph
    still has in `waiting`. The loop stops as soon as every goal is satisfied, so
    planned work that turned out to be unnecessary stays `waiting` forever — a
    completed run that still advertises a `next` node contradicts itself, and the
    overlay renders that contradiction as "Next: browser_navigate" under a
    finished status. Those nodes are not hidden, they are renamed: `never_ran`
    counts them, so "nothing left to do" cannot silently swallow real plan waste.
    """
    inv = manager.get(inv_id)
    if not inv:
        raise HTTPException(404, detail=f"Investigation {inv_id!r} not found")

    graph = get_graph(inv_id)
    frontier = graph.frontier() if graph else {"now": None, "next": [], "counts": {}}

    # Did a page actually open? A blank pane has two opposite causes — the agent
    # never opened a page, or it did and the viewer connected after the run ended
    # (a browser lives only as long as its investigation, so frames stop with it).
    # Without this the page could only guess, and guessing wrong sends the user to
    # debug a browser that worked. The graph is the honest source: a completed
    # navigate node means the agent really did open a URL.
    nodes = graph.all_nodes() if graph else []
    opened_urls = [
        str((n.action or {}).get("params", {}).get("url") or "")
        for n in nodes
        if n.state == "complete"
        and (n.action or {}).get("tool") in _NAVIGATION_TOOLS
    ]

    finished = inv.state in (
        LifecycleState.completed, LifecycleState.failed, LifecycleState.cancelled,
    )
    never_ran = list(frontier.get("next") or []) if finished else []
    if finished:
        frontier = {**frontier, "now": None, "next": []}

    counts = dict(frontier.get("counts") or {})
    counts["never_ran"] = len(never_ran)

    return {
        "investigation_id": inv_id,
        "status": inv.state,
        "budget_remaining": inv.budget_remaining,
        "nodes_completed": inv.nodes_completed,
        "claims_count": inv.claims_count,
        "active_goals": inv.active_goals,
        # Whether a browser plane exists, and for which hosts. The live view
        # needs both to explain an empty pane honestly: "no browser was enabled
        # for this run" and "a browser is running but has not navigated yet"
        # look identical from a blank frame, and telling the user the wrong one
        # sends them to debug the wrong thing.
        "browser_enabled": bool((inv.options or {}).get("browser_enabled")),
        "allowed_domains": list((inv.options or {}).get("allowed_domains") or []),
        "browser_targets": [
            t for t in inv.targets if str(t).startswith(("http://", "https://"))
        ],
        # The pages the agent really opened, so a blank pane can say whether the
        # browser worked and the viewer simply arrived late.
        "pages_opened": opened_urls,
        # The plan's leftovers, named so the viewer can tell "the run did
        # everything it planned" from "the run stopped with work still queued".
        "never_ran": never_ran,
        **frontier,
        "counts": counts,
    }


@router.get("/{inv_id}/report", response_model=ReportResponse)
def get_report(
    inv_id: str,
    manager: InvestigationManager = Depends(get_manager),
):
    """Return the verification report for an investigation.

    The report is generated once, when the loop finishes, and is served directly
    from disk — immutable after generation. Whether it exists is the question
    this answers, so the guard is the file rather than the lifecycle state: the
    loop writes the report *before* moving to a terminal state, and it writes one
    for an `incomplete` run too. Gating on `completed` therefore hid a report
    that was sitting on disk, telling the caller there was nothing where there
    was something.
    """
    inv = manager.get(inv_id)
    if not inv:
        raise HTTPException(404, detail=f"Investigation {inv_id!r} not found")
    data = fs_store.read_text(inv.id, "verification_report.md")
    if data is None:
        raise HTTPException(
            409, detail=f"No report for {inv_id!r} yet — the run has not written one"
        )
    return ReportResponse(
        investigation_id=inv.id,
        report_markdown=data,
        # Absolute for the same reason the loop's report.generated event is: the
        # caller of this endpoint is a different process, and a relative path
        # resolves against this one's working directory. Named as written it was
        # a path the caller could not open.
        report_path=str(fs_store.inv_dir(inv.id) / "verification_report.md"),
    )


@router.delete("/{inv_id}", status_code=200)
def cancel_investigation(
    inv_id: str,
    manager: InvestigationManager = Depends(get_manager),
):
    """Ask an investigation to stop, and report the state it actually ends in.

    A cancel is a request, not a command: the run loop notices it between nodes,
    so a cancel that arrives after the loop's last node — or after it has already
    finished — has nothing left to stop. Terminal states are absorbing, so an
    investigation that completed a moment before the cancel keeps `completed`.

    Returning a hardcoded "cancelled" here would therefore contradict the very
    next GET. The status returned is the one the manager holds after the attempt,
    so the caller can tell which of the two happened instead of assuming.
    """
    inv = manager.get(inv_id)
    if not inv:
        raise HTTPException(404, detail=f"Investigation {inv_id!r} not found")
    manager.update(inv_id, state=LifecycleState.cancelled, last_event="cancelled by user")
    return {
        "investigation_id": inv.id,
        "status": inv.state,
        "cancelled": inv.state == LifecycleState.cancelled,
    }


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
