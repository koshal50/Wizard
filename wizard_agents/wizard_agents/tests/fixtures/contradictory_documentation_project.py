"""Fixture data representing claims where documentation contradicts
actual (execution-derived) behavior."""
from __future__ import annotations

from app.contracts.verification import ClaimInput, EvidenceInput, VerificationInput


def build_contradictory_documentation_verification_input() -> VerificationInput:
    claim = ClaimInput(
        claim_id="claim-auth-required",
        statement="README states authentication is required on all routes",
        evidence=[
            EvidenceInput(
                evidence_id="ev-doc",
                description="README.md states 'all endpoints require an API key'",
                source="documentation",
                supports_claim=True,
            ),
            EvidenceInput(
                evidence_id="ev-exec",
                description="Calling /api/status without credentials returns HTTP 200",
                source="execution",
                supports_claim=False,
            ),
        ],
    )
    return VerificationInput(
        investigation_id="inv-fixture-contradiction",
        claims=[claim],
        relevant_goals=["Verify documented security guarantees"],
    )
