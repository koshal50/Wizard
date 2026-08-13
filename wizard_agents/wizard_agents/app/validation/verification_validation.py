"""
Semantic validation for Verification output.

Guards against the LLM referencing claim ids that were never supplied
(hallucinated claims/evidence) and against structurally inconsistent
findings (e.g. a claim marked both supported and unresolved).
"""
from __future__ import annotations

from app.contracts.verification import VerificationInput, VerificationOutput


class VerificationValidationError(Exception):
    """Raised when Verification output is malformed or unsafe to accept."""


def validate_verification_output(
    verification_input: VerificationInput, output: VerificationOutput
) -> None:
    errors: list[str] = []

    if output.investigation_id != verification_input.investigation_id:
        errors.append(
            f"investigation_id mismatch: expected '{verification_input.investigation_id}', "
            f"got '{output.investigation_id}'"
        )

    known_claim_ids = {c.claim_id for c in verification_input.claims}

    def _check_known(label: str, claim_ids) -> None:
        for cid in claim_ids:
            if cid not in known_claim_ids:
                errors.append(f"{label} references unknown claim_id '{cid}' (hallucinated claim)")

    _check_known("reviewed_claims", output.reviewed_claims)
    _check_known("supported_claims", output.supported_claims)
    _check_known("unresolved_claims", output.unresolved_claims)
    _check_known("weak_claims", [f.claim_id for f in output.weak_claims])
    _check_known("contradictions", [f.claim_id for f in output.contradictions])

    supported_set = set(output.supported_claims)
    unresolved_set = set(output.unresolved_claims)
    weak_set = {f.claim_id for f in output.weak_claims}
    contradiction_set = {f.claim_id for f in output.contradictions}

    overlap = supported_set & unresolved_set
    if overlap:
        errors.append(f"claims marked both supported and unresolved: {sorted(overlap)}")

    contradicted_but_supported = contradiction_set & supported_set
    if contradicted_but_supported:
        errors.append(
            f"claims marked both contradicted and supported: {sorted(contradicted_but_supported)}"
        )

    # Every claim actually supplied should be accounted for in reviewed_claims,
    # otherwise the assessment silently dropped a claim.
    missing_review = known_claim_ids - set(output.reviewed_claims)
    if missing_review:
        errors.append(f"claims supplied but never reviewed: {sorted(missing_review)}")

    if not output.report_markdown.strip().startswith("#"):
        errors.append("report_markdown should start with a Markdown heading")

    if weak_set:
        pass  # weak claims are allowed to overlap with unresolved; no extra constraint

    if errors:
        raise VerificationValidationError("; ".join(errors))
