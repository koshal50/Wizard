"""Revoke only the current CLI credential, independently of the browser session."""

from wizard.cli.account_login import APIError, LoginError, LoginFlow, account_origin
from wizard.cli.account_session import generation, session_guard
from wizard.cli.account_storage import CredentialStore, StorageError

LOGGED_OUT = "Youve been logged out of Wizard."
ALREADY_OUT = "Youre already logged out."
LOCAL_ONLY = "Logged out locally. Could not revoke the server credential."


def logout(origin=None, store=None, client=None, on_removed=None):
    origin = origin or account_origin()
    store = store or CredentialStore(origin)
    proofs = {}
    with session_guard(store) as stream:
        # Advance even if secure removal fails: older logins must never persist.
        generation(store, stream, advance=True)
        existing = store.load()
        if existing is not None and not isinstance(existing, dict):
            raise StorageError("Account credential storage contains invalid data")
        if hasattr(store, "pending_store"):
            pending = store.pending_store()
            proofs = pending.load() or {}
            if not isinstance(proofs, dict) or not all(
                isinstance(proof, dict) for proof in proofs.values()
            ):
                raise StorageError(
                    "Pending account authorization storage contains invalid data"
                )
        store.delete()
        if on_removed:
            on_removed()
        if hasattr(store, "pending_store"):
            pending.delete()
    token = (existing or {}).get("access_token")
    if not token and not proofs:
        return ALREADY_OUT
    flow = None
    try:
        flow = LoginFlow(origin, store=store, client=client)
        revoked = True
        if token:
            try:
                response = flow.call(
                    "/api/account/credential", token=token, method="DELETE"
                )
                revoked = response.get("revoked") is True
            except APIError as exc:
                revoked = exc.status == 401
            except LoginError:
                revoked = False
        for proof in proofs.values():
            try:
                cancelled = flow.call("/api/cli/cancel", proof)
                revoked = revoked and cancelled.get("state") == "cancelled"
            except APIError as exc:
                revoked = revoked and exc.status in {404, 410}
            except LoginError:
                revoked = False
        return LOGGED_OUT if revoked else LOCAL_ONLY
    except (LoginError, StorageError):
        return LOCAL_ONLY
    finally:
        if flow:
            flow.close()


def terminal_logout(console):
    try:
        console.print(logout(), markup=False)
        return 0
    except (LoginError, StorageError) as exc:
        console.print("Logout failed. " + str(exc), markup=False)
        return 1
