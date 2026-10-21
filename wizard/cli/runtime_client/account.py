"""Attach the current secure CLI credential to runtime accounting requests."""

from wizard.cli.account_login import LoginError, account_origin
from wizard.cli.account_session import session_guard
from wizard.cli.account_storage import CredentialStore


def account_headers():
    try:
        origin = account_origin()
    except LoginError:
        return {}  # Account login is optional for existing local-profile users.
    store = CredentialStore(origin)
    with session_guard(store):
        saved = store.load()
    if not saved or not saved.get("access_token"):
        return {}
    return {"Authorization": "Bearer " + saved["access_token"]}
