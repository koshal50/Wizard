from __future__ import annotations

import pytest
from app.contracts.verification import (
    VerificationInput,
    VerificationOutput,
)
from app.llm.base import LLMError, LLMProvider
from app.validation.verification_validation import (
    VerificationValidationError,
    validate_verification_output,
)
from app.verification.agent import VerificationAgent, VerificationAgentError
from pydantic import ValidationError


@pytest.mark.parametrize('command,target', [('investigate', 'api'), ('explain', 'architecture'), ('verify', 'runtime'), ('report', None)])
def test_dynamic_report_contract_reaches_provider_prompt(supported_claim, command, target):
    import json

    from app.prompts.verification_prompts import build_verification_user_prompt

    contract = {'command': command, 'targets': [target] if target else [],
                'question': 'Describe only the selected subject',
                'sections': {target: ['Routes and handlers']} if target else {}}
    vi = VerificationInput(investigation_id='inv-1', claims=[supported_claim],
                           context=json.dumps({'report_contract': contract}))
    prompt = build_verification_user_prompt(vi)
    assert json.dumps(vi.model_dump(mode='json'), indent=2) in prompt
    assert 'report_contract in context is authoritative' in prompt
    assert 'Cite supplied obs_ observation IDs in EVERY narrative paragraph' in prompt
    assert 'Do not repeat universal metadata' in prompt
    assert 'Repository reads support inspected knowledge' in prompt


def test_report_heading_is_enforced_in_provider_schema():
    assert VerificationOutput.model_json_schema()['properties']['report_markdown']['pattern'] == '^#'
    with pytest.raises(ValidationError, match='pattern'):
        VerificationOutput(investigation_id='inv', overall_assessment='sufficient',
                           reasoning='Observed evidence', report_markdown='Plain text without a heading')


def test_supported_claim_is_marked_supported(mock_llm, supported_claim):
    vi = VerificationInput(investigation_id="inv-1", claims=[supported_claim])
    agent = VerificationAgent(mock_llm)
    out = agent.verify(vi)
    assert supported_claim.claim_id in out.supported_claims


def test_weak_claim_is_flagged(mock_llm, weak_claim):
    vi = VerificationInput(investigation_id="inv-1", claims=[weak_claim])
    agent = VerificationAgent(mock_llm)
    out = agent.verify(vi)
    weak_ids = {f.claim_id for f in out.weak_claims}
    assert weak_claim.claim_id in weak_ids


def test_contradictory_evidence_flagged(mock_llm, contradicted_claim):
    vi = VerificationInput(investigation_id="inv-1", claims=[contradicted_claim])
    agent = VerificationAgent(mock_llm)
    out = agent.verify(vi)
    contradiction_ids = {f.claim_id for f in out.contradictions}
    assert contradicted_claim.claim_id in contradiction_ids
    assert contradicted_claim.claim_id in out.unresolved_claims


def test_missing_evidence_flagged(mock_llm, missing_evidence_claim):
    vi = VerificationInput(investigation_id="inv-1", claims=[missing_evidence_claim])
    agent = VerificationAgent(mock_llm)
    out = agent.verify(vi)
    assert any(missing_evidence_claim.claim_id in m for m in out.missing_evidence)


def test_multiple_claims_all_reviewed(mock_llm, verification_input_multi):
    agent = VerificationAgent(mock_llm)
    out = agent.verify(verification_input_multi)
    expected_ids = {c.claim_id for c in verification_input_multi.claims}
    assert expected_ids.issubset(set(out.reviewed_claims))


def test_unresolved_claim_present_for_contradiction(mock_llm, verification_input_multi):
    agent = VerificationAgent(mock_llm)
    out = agent.verify(verification_input_multi)
    assert "claim-contradicted" in out.unresolved_claims


def test_malformed_input_rejected_by_pydantic():
    with pytest.raises(ValidationError):
        VerificationInput(investigation_id="inv-1", claims=[])  # min_length=1


def test_malformed_llm_output_raises_agent_error(verification_input_multi):
    class BrokenProvider(LLMProvider):
        @property
        def name(self) -> str:
            return "broken"

        def generate_structured(self, *args, **kwargs):
            raise LLMError("simulated malformed response")

    agent = VerificationAgent(BrokenProvider())
    with pytest.raises(VerificationAgentError):
        agent.verify(verification_input_multi)


def test_hallucinated_evidence_claim_id_rejected(verification_input_multi):
    output = VerificationOutput(
        investigation_id=verification_input_multi.investigation_id,
        overall_assessment="ok",
        reviewed_claims=[c.claim_id for c in verification_input_multi.claims],
        supported_claims=["claim-that-does-not-exist"],
        reasoning="r",
        report_markdown="# report",
    )
    with pytest.raises(VerificationValidationError):
        validate_verification_output(verification_input_multi, output)


def test_markdown_generation_present(mock_llm, verification_input_multi):
    agent = VerificationAgent(mock_llm)
    out = agent.verify(verification_input_multi)
    assert out.report_markdown.strip().startswith("#")
    assert "Verification Report" in out.report_markdown


def test_claim_marked_supported_and_unresolved_rejected(verification_input_multi):
    claim_id = verification_input_multi.claims[0].claim_id
    output = VerificationOutput(
        investigation_id=verification_input_multi.investigation_id,
        overall_assessment="ok",
        reviewed_claims=[c.claim_id for c in verification_input_multi.claims],
        supported_claims=[claim_id],
        unresolved_claims=[claim_id],
        reasoning="r",
        report_markdown="# report",
    )
    with pytest.raises(VerificationValidationError):
        validate_verification_output(verification_input_multi, output)
