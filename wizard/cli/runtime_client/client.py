"""Runtime Engine client — Step 4 of the CLI pipeline.

Sends InvestigationRequests to the Runtime Engine and receives responses.

CURRENT STATE: The Runtime Engine does not exist yet. This module contains
a stub implementation that acknowledges the request and returns a placeholder
response. When the Runtime Engine API is defined (by Shivam), only this
file needs to change.

The CLI code upstream (commands, parser, intent builder) and downstream
(display) will remain untouched — this is the single integration point.

Future integration points (to be defined by Runtime Engine contributor):
    - POST endpoint for submitting InvestigationRequests
    - GET endpoint for polling investigation progress
    - GET endpoint for retrieving the final report
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from wizard.cli.models.investigation_request import InvestigationRequest


@dataclass
class RuntimeResponse:
    """Response received from the Runtime Engine.

    Attributes:
        status: Response status — "accepted", "in_progress", "completed",
                "failed", or "engine_unavailable".
        message: Human-readable status message.
        data: Arbitrary response data from the Runtime Engine.
        timestamp: When the response was created.
    """

    status: str
    message: str
    data: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------------------------
# Stub Implementation
# ---------------------------------------------------------------------------
# TODO: Replace with actual HTTP client when Runtime Engine API is defined.
#
# Expected future implementation:
#   1. Serialize request.to_dict() to JSON
#   2. POST to Runtime Engine endpoint
#   3. Poll progress endpoint for updates
#   4. Return final RuntimeResponse
#
# The CLI's display layer will render whatever RuntimeResponse contains.
# ---------------------------------------------------------------------------

import urllib.request
import urllib.error
import time
from rich.console import Console

console = Console()

def send_request(request: InvestigationRequest) -> RuntimeResponse:
    """Send an InvestigationRequest to the Runtime Engine via HTTP.

    Args:
        request: The fully assembled InvestigationRequest.

    Returns:
        RuntimeResponse from the Runtime Engine.
    """
    # Map CLI Request to Runtime Engine API Request format
    api_payload = {
        "repository_path": request.repository.path,
        "intent": request.intent.action,
        "targets": request.intent.targets,
        "options": request.options.to_dict()
    }
    
    base_url = "http://127.0.0.1:8080/v1/investigations"
    
    # 1. Start investigation
    try:
        req = urllib.request.Request(
            base_url,
            data=json.dumps(api_payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            inv_id = data.get("investigation_id")
    except urllib.error.URLError as e:
        return RuntimeResponse(
            status="engine_unavailable",
            message=f"Could not connect to Runtime Engine at {base_url}. Is it running?",
            data={"error": str(e)}
        )

    # 2. Poll events until completed/failed
    seq = 0
    current_state = "unknown"
    status_data = {}
    while True:
        try:
            events_url = f"{base_url}/{inv_id}/events?since_seq={seq}"
            req = urllib.request.Request(events_url, method='GET')
            with urllib.request.urlopen(req) as response:
                events = json.loads(response.read().decode())
                
                for ev in events:
                    seq = max(seq, ev["seq"])
                    ev_type = ev["event_type"]
                    payload = ev["payload"]
                    
                    if ev_type == "node.completed":
                        console.print(f"[green]✔[/green] Completed node [bold]{payload.get('node_id')}[/bold]")
                    elif ev_type == "node.failed":
                        console.print(f"[red]✖[/red] Failed node [bold]{payload.get('node_id')}[/bold] ({payload.get('reason', 'execution_failed')})")
                    elif ev_type == "claim.admitted":
                        console.print(f"  [cyan]↳[/cyan] Found evidence: {payload.get('claim_type')} -> {payload.get('key')}")
                    elif ev_type == "goal.satisfied":
                        console.print(f"🏆 [bold yellow]Goal Satisfied:[/bold yellow] {payload.get('goal_name')}")
                    elif ev_type == "agent.consulted":
                        console.print(f"[blue]🤖[/blue] Consulted Agent ({payload.get('agent_type')})")
                        
            # Check status
            status_req = urllib.request.Request(f"{base_url}/{inv_id}", method='GET')
            with urllib.request.urlopen(status_req) as response:
                status_data = json.loads(response.read().decode())
                current_state = status_data.get("status", "unknown")
                
                if current_state in ("completed", "failed", "cancelled"):
                    break
                    
        except urllib.error.URLError as e:
            # Engine might have crashed or we lost connection
            console.print(f"[red]Connection lost or error while polling:[/red] {e}")
            break
            
        time.sleep(1.0)
        
    # 3. Fetch report if completed
    report_data = {}
    try:
        if current_state == "completed":
            report_req = urllib.request.Request(f"{base_url}/{inv_id}/report", method='GET')
            with urllib.request.urlopen(report_req) as response:
                report_data = json.loads(response.read().decode())
    except urllib.error.HTTPError:
        pass

    return RuntimeResponse(
        status=current_state,
        message=f"Investigation finished with status: {current_state}",
        data={
            "request": api_payload,
            "report_markdown": report_data.get("report_markdown", "No report available."),
            "stats": status_data
        }
    )

