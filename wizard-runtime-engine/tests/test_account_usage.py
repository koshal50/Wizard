"""Permanent ownership survives process restoration and reused submission/session IDs."""

import hashlib
import json
from uuid import uuid4

import pytest

from wizard_kernel.contracts.request import InvestigationRequest
from wizard_kernel.session.manager import InvestigationManager
from wizard_kernel.storage.usage import get_usage


def test_restored_investigation_retains_account_and_rejects_other_owner(tmp_path, monkeypatch):
    monkeypatch.setenv("WIZARD_DATA_DIR", str(tmp_path))
    first, second = str(uuid4()), str(uuid4())
    request = InvestigationRequest(
        repository_path=str(tmp_path),
        intent="verify",
        session_id="reused-session",
        idempotency_key="same-submission",
    )
    manager = InvestigationManager()
    inv = manager.create(request, account_id=first)
    session = inv.usage_session_id
    assert get_usage().runs[inv.id]["profile_id"] == "account:" + first
    restored = InvestigationManager()
    assert restored.restore() == 1
    assert restored.get(inv.id).account_id == first
    assert restored.create(request, account_id=first).id == inv.id
    with pytest.raises(ValueError, match="different account"):
        restored.create(request, account_id=second)
    # Re-observation after restart must not hash the saved session key again.
    get_usage().begin(restored.get(inv.id))
    assert get_usage().runs[inv.id]["session_id"] == session
    assert get_usage().runs[inv.id]["profile_id"] == "account:" + first
    request.idempotency_key = "new-submission"
    different = restored.create(request, account_id=second)
    assert different.usage_session_id != session
    assert get_usage().runs[different.id]["profile_id"] == "account:" + second


def test_anonymous_submission_signature_stays_compatible_with_saved_history(tmp_path, monkeypatch):
    monkeypatch.setenv("WIZARD_DATA_DIR", str(tmp_path))
    request = InvestigationRequest(repository_path=str(tmp_path), intent="report")
    expected = hashlib.sha256(
        json.dumps(request.model_dump(exclude={"idempotency_key"}), sort_keys=True).encode()
    ).hexdigest()
    inv = InvestigationManager().create(request)
    assert inv.submission_hash == expected
    assert inv.account_id is None
