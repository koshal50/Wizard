import httpx
import pytest

from backend.tests.test_architecture_contract import graph
from wizard.cli.runtime_client import architecture


def test_no_network_without_consent_or_login(monkeypatch):
    monkeypatch.setattr(architecture, "account_origin", lambda: "https://wizard.test")
    monkeypatch.setattr(architecture, "account_headers", dict)
    monkeypatch.setattr(httpx, "Client", lambda **kw: pytest.fail("Network must not be used"))
    with pytest.raises(ValueError, match="consent"):
        architecture.upload(graph())
    with pytest.raises(ValueError, match="/login"):
        architecture.upload(graph(), consent=True)


@pytest.mark.parametrize("status", [401, 403, 413, 422, 500, 503, 302])
def test_failures_never_return_success_url(monkeypatch, status):
    monkeypatch.setattr(architecture, "account_origin", lambda: "https://wizard.test")
    monkeypatch.setattr(architecture, "account_headers", lambda: {"Authorization": "Bearer test"})
    original = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(
        lambda request: httpx.Response(status, json={"error": "failure"})), **kw))
    with pytest.raises(ValueError) as exc:
        architecture.upload(graph(), consent=True)
    assert "saved successfully" not in str(exc.value) and "/investigations/" not in str(exc.value)


def test_upload_prints_configured_url_only_after_created(monkeypatch):
    from uuid import uuid4
    public_id = str(uuid4())
    monkeypatch.setattr(architecture, "account_origin", lambda: "https://wizard.test")
    monkeypatch.setattr(architecture, "account_headers", lambda: {"Authorization": "Bearer test"})
    def respond(request):
        assert request.url == "https://wizard.test/api/investigations"
        assert request.headers["authorization"] == "Bearer test"
        return httpx.Response(201, json={"investigation_id": public_id})
    original = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: original(transport=httpx.MockTransport(respond), **kw))
    result = architecture.upload(graph(), consent=True)
    assert "saved successfully" in result and "Nodes: 2" in result and "Relationships: 1" in result
    assert result.endswith("https://wizard.test/investigations/" + public_id)
