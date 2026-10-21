"""Unit transports must never attach the developer's real account credential."""

import pytest


@pytest.fixture(autouse=True)
def isolated_runtime_account_headers(monkeypatch):
    monkeypatch.setattr("wizard.cli.runtime_client.account.account_headers", dict)
