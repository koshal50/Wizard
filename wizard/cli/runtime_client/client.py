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

def send_request(request: InvestigationRequest) -> RuntimeResponse:
    """Send an InvestigationRequest to the Runtime Engine.

    Currently returns a stub response acknowledging the request.
    This is the ONLY function that needs to change when the Runtime
    Engine is implemented.

    Args:
        request: The fully assembled InvestigationRequest.

    Returns:
        RuntimeResponse from the Runtime Engine (currently a stub).
    """
    # Serialize the request for logging / future transmission
    request_payload = request.to_dict()

    # --- STUB: Simulate Runtime Engine acknowledgement ---
    target_desc = ", ".join(request.intent.targets) if request.intent.targets else "all"

    return RuntimeResponse(
        status="accepted",
        message=(
            f"Investigation request accepted. "
            f"Action: {request.intent.action} | "
            f"Target: {target_desc} | "
            f"Repository: {request.repository.path}"
        ),
        data={
            "request": request_payload,
            "engine_status": "stub",
            "note": (
                "The Runtime Engine is not yet implemented. "
                "This response confirms the CLI pipeline is working correctly. "
                "The request payload above is exactly what will be sent to the "
                "Runtime Engine when it is available."
            ),
        },
    )
