"""
Verification Agent contracts.

Verification REVIEWS claims and evidence and produces a structured,
markdown-rendered assessment. It never modifies the Claims Graph, trust
scores, or goal completion state -- that remains Runtime's responsibility.
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from app.contracts.common import Severity


class EvidenceSource(str, Enum):
    EXECUTION = "execution"
    DOCUMENTATION = "documentation"
    STATIC_ANALYSIS = "static_analysis"
    CONFIGURATION = "configuration"
    OTHER = "other"


class EvidenceInput(BaseModel):
    """A single piece of evidence (observation) tied to a claim."""

    evidence_id: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    source: EvidenceSource = EvidenceSource.OTHER
    supports_claim: bool = Field(
        default=True, description="True if this evidence supports the claim, False if it contradicts it"
    )
    node_id: Optional[str] = Field(default=None, description="Investigation node this evidence came from")


class ClaimInput(BaseModel):
    """A claim from the Claims Graph, along with its attached evidence."""

    claim_id: str = Field(..., min_length=1)
    statement: str = Field(..., min_length=1)
    node_id: Optional[str] = None
    evidence: List[EvidenceInput] = Field(default_factory=list)
    trust_score: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, description="Optional trust score supplied by Runtime, read-only"
    )

    @property
    def supporting_evidence(self) -> List[EvidenceInput]:
        return [e for e in self.evidence if e.supports_claim]

    @property
    def contradicting_evidence(self) -> List[EvidenceInput]:
        return [e for e in self.evidence if not e.supports_claim]

    @property
    def has_execution_evidence(self) -> bool:
        return any(e.source == EvidenceSource.EXECUTION for e in self.evidence)


class VerificationInput(BaseModel):
    """Everything Verification needs to critically review a set of claims."""

    investigation_id: str = Field(..., min_length=1)
    claims: List[ClaimInput] = Field(..., min_length=1)
    contradictory_evidence: List[EvidenceInput] = Field(
        default_factory=list, description="Evidence that doesn't map cleanly to a single claim_id"
    )
    relevant_goals: List[str] = Field(default_factory=list)
    context: Optional[str] = None
    trust_information: Optional[str] = Field(
        default=None, description="Optional free-text trust context supplied by Runtime"
    )


class VerificationFinding(BaseModel):
    """A single structured finding Verification makes about a claim."""

    claim_id: str
    finding: str = Field(..., min_length=1)
    severity: Severity = Severity.LOW
    rationale: str = Field(..., min_length=1)


class VerificationOutput(BaseModel):
    """Verification's structured assessment. `report_markdown` is the
    human-facing artifact; the other fields let Runtime consume the
    assessment programmatically before it writes verification_report.md.
    """

    investigation_id: str
    overall_assessment: str = Field(..., min_length=1)
    reviewed_claims: List[str] = Field(default_factory=list, description="claim_ids reviewed")
    supported_claims: List[str] = Field(default_factory=list, description="claim_ids judged well-supported")
    weak_claims: List[VerificationFinding] = Field(default_factory=list)
    contradictions: List[VerificationFinding] = Field(default_factory=list)
    missing_evidence: List[str] = Field(default_factory=list, description="Descriptions of evidence gaps")
    unresolved_claims: List[str] = Field(default_factory=list, description="claim_ids that remain undecided")
    recommended_additional_investigations: List[str] = Field(default_factory=list)
    reasoning: str = Field(..., min_length=1)
    report_markdown: str = Field(..., min_length=1)

    @field_validator("reviewed_claims")
    @classmethod
    def _reviewed_not_empty_if_supplied(cls, v: List[str]) -> List[str]:
        return v
