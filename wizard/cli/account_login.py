"""Website-to-terminal login protocol; runtime/provider settings are never read or written."""

import hashlib
import os
import re
import secrets
import threading
import webbrowser
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx

from wizard.cli.account_session import current_generation, generation, session_guard
from wizard.cli.account_storage import CredentialStore, StorageError

ACCOUNT_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class LoginError(Exception):
    pass


class APIError(LoginError):
    def __init__(self, code, status=0):
        self.code, self.status = code, status
        guidance = {
            "invalid_code": "Check the code shown by the website and try again.",
            "approval_required": "Authenticate and explicitly approve in the website first.",
            "rate_limited": "Wait at least 60 seconds before trying again.",
            "attempt_limit": "Cancel and start a new /login request.",
            "code_expired": "Cancel and start a new /login request.",
            "expired_or_cancelled": "Start a new /login request.",
        }.get(code, "")
        super().__init__(
            f"Account authorization: {code} (HTTP {status}). {guidance}".rstrip()
        )


def account_origin():
    from dotenv import dotenv_values

    from backend.config import origin

    # Use Wizard's configuration, never the repository being investigated.
    try:
        configured = dotenv_values(ACCOUNT_ENV_FILE, interpolate=False)
    except OSError:
        raise LoginError("Could not read Wizard's account configuration.") from None
    value = os.environ.get("WIZARD_ACCOUNT_URL", configured.get("WIZARD_ACCOUNT_URL"))
    if not value:
        raise LoginError(
            "Set WIZARD_ACCOUNT_URL in Wizard's .env or your environment to the website account service origin."
        )
    try:
        return origin(
            value,
            os.environ.get(
                "WIZARD_ACCOUNT_LOCAL_DEV", configured.get("WIZARD_ACCOUNT_LOCAL_DEV")
            )
            == "1",
        )
    except ValueError:
        raise LoginError(
            "WIZARD_ACCOUNT_URL requires HTTPS; loopback HTTP requires WIZARD_ACCOUNT_LOCAL_DEV=1."
        ) from None


def expiry(value):
    try:
        when = datetime.fromisoformat(value)
        if when.tzinfo is None or when <= datetime.now(UTC):
            raise ValueError()
        return when
    except (ValueError, TypeError, AttributeError):
        raise LoginError(
            "Account service returned an invalid or expired credential/request."
        ) from None


class LoginFlow:
    _lock = threading.Lock()

    def __init__(
        self, origin=None, client=None, store=None, opener=None, cancel_event=None
    ):
        self.cancel_event = cancel_event or threading.Event()
        self.origin = origin or account_origin()
        self.store = store or CredentialStore(self.origin)
        self.generation = current_generation(self.store)
        self.client = client or httpx.Client(
            base_url=self.origin,
            timeout=httpx.Timeout(8, connect=3),
            follow_redirects=False,
            trust_env=False,
        )
        self.owns_client = client is None
        self.opener = opener or webbrowser.open
        self.verifier = secrets.token_urlsafe(32)
        self.rid = None
        self.active = False
        self.complete = False
        self.account = None
        self.expires_at = None
        self._held_lock = False
        self._closed = False

    def call(self, path, data=None, token=None, method="POST"):
        try:
            response = self.client.request(
                method,
                self.origin + path,
                json=data,
                headers={"Authorization": "Bearer " + token} if token else {},
            )
        except httpx.HTTPError:
            raise LoginError(
                "Account service connection failed or timed out. Retry /login; no existing credential was changed."
            ) from None
        try:
            result = response.json()
        except (ValueError, TypeError):
            raise LoginError("Account service returned a malformed response.") from None
        if not isinstance(result, dict):
            raise LoginError("Account service returned a malformed response.")
        if response.status_code >= 300:
            code = result.get("error", "request_failed")
            if not isinstance(code, str) or not re.fullmatch("[a-z_]{1,80}", code):
                code = "request_failed"
            raise APIError(code, response.status_code)
        return result

    def proof(self):
        return {"request_id": self.rid, "verifier": self.verifier}

    def cancelled(self):
        return (
            self.cancel_event.is_set()
            or current_generation(self.store) != self.generation
        )

    def authenticated_account(self, existing):
        """Verify a saved credential without starting a browser authorization."""
        if not isinstance(existing, dict) or not existing.get("access_token"):
            return None
        if self.cancelled():
            raise LoginError("Account authorization cancelled.")
        try:
            expiry(existing.get("expires_at"))
        except LoginError:
            return None
        try:
            verified = self.call(
                "/api/account/me", token=existing["access_token"], method="GET"
            )
        except APIError as exc:
            if exc.status == 401:
                return None
            raise
        account = verified.get("account")
        if self.cancelled():
            raise LoginError("Account authorization cancelled.")
        if not isinstance(account, dict) or not all(
            isinstance(account.get(k), str) and account[k]
            for k in ("id", "email", "full_name")
        ):
            raise LoginError("Account service returned an invalid account response.")
        return account

    def start(self):
        if self.active or not self._lock.acquire(blocking=False):
            raise LoginError(
                "A /login request is already active. Complete or cancel it first."
            )
        self._held_lock = True
        self.active = True
        try:
            if self.cancelled():
                raise LoginError("Account authorization cancelled.")
            # Fail before remote issuance if the secure store cannot be read.
            existing = self.store.load()
            self.account = self.authenticated_account(existing)
            if self.account:
                self.complete = True
                self.close()
                return "You are already authenticated with your Wizard website account."
            previous = (
                "Existing account credentials will be preserved until replacement succeeds.\n"
                if existing
                else ""
            )
            data = self.call(
                "/api/cli/requests",
                {"verifier_hash": hashlib.sha256(self.verifier.encode()).hexdigest()},
            )
            rid = data.get("request_id", "")
            from uuid import UUID

            try:
                self.rid = str(UUID(rid))
            except (ValueError, TypeError, AttributeError):
                raise LoginError(
                    "Account service returned an invalid request identifier."
                ) from None
            self.expires_at = expiry(data.get("expires_at"))
            if self.cancelled():
                raise LoginError("Account authorization cancelled.")
            if hasattr(self.store, "pending_store"):
                with session_guard(self.store) as stream:
                    if (
                        generation(self.store, stream) != self.generation
                        or self.cancel_event.is_set()
                    ):
                        raise LoginError("Account authorization cancelled.")
                    pending = self.store.pending_store()
                    proofs = pending.load() or {}
                    proofs[self.rid] = self.proof()
                    pending.save(proofs)
            url = data.get("authorization_url", "")
            if not isinstance(url, str):
                raise LoginError("Account service returned a malformed browser URL.")
            try:
                parsed = urlsplit(url)
                fragment = parse_qs(parsed.fragment)
            except ValueError:
                raise LoginError(
                    "Account service returned a malformed browser URL."
                ) from None
            if (
                parsed.scheme + "://" + parsed.netloc != self.origin
                or parsed.path != "/cli/authorize"
                or parsed.query
                or fragment.get("request_id") != [self.rid]
                or not re.fullmatch(
                    "[A-Za-z0-9_-]{43}", fragment.get("ticket", [""])[0]
                )
            ):
                raise LoginError("Account service returned an unsafe browser URL.")
            try:
                opened = self.opener(url)
            except Exception:  # noqa: BLE001 -- isolate platform browser/worker errors from secrets
                opened = False
            return (
                previous
                + ("Browser opened. " if opened else "Browser could not open. ")
                + (
                    "Open this URL manually:\n"
                    + url
                    + "\nAuthenticate, explicitly approve, then paste the code here. "
                    "Use /cancel-login to cancel. Request expires at "
                    + self.expires_at.isoformat()
                )
            )
        except BaseException:
            self.close(cancel=True)
            raise

    def submit(self, code):
        if self.cancelled():
            raise LoginError(
                "Account authorization cancelled; remote cancellation will be attempted."
            )
        if not self.active or not self.rid:
            raise LoginError("No login is pending. Run /login.")
        if self.expires_at <= datetime.now(UTC):
            raise LoginError(
                "Authorization request expired. Cancel and start /login again."
            )
        normalized = code.replace("-", "").replace(" ", "").upper()
        if not re.fullmatch("[A-F0-9]{12}", normalized):
            raise LoginError(
                "Enter the 12-character hexadecimal code shown by the website."
            )
        try:
            data = self.call("/api/cli/exchange", {**self.proof(), "code": normalized})
        except LoginError as exc:
            # A write may have committed. Recovery is proof-bearing and cannot consume another code.
            if isinstance(exc, APIError) and exc.code not in {
                "already_exchanged",
                "service_unavailable",
            }:
                raise
            try:
                data = self.call("/api/cli/recover", self.proof())
            except LoginError:
                raise LoginError(
                    "Exchange outcome could not be recovered. Cancel to revoke any issuance, then restart /login. Existing credentials are unchanged."
                ) from None
        if self.cancelled():
            raise LoginError(
                "Account authorization cancelled after exchange; remote revocation will be attempted."
            )
        token = data.get("access_token", "")
        if (
            not isinstance(token, str)
            or not re.fullmatch(r"wa_" + re.escape(self.rid) + r"\.[a-f0-9]{64}", token)
            or data.get("token_type") != "Bearer"
        ):
            raise LoginError(
                "Account service returned malformed credentials. Cancel and restart /login."
            )
        expiry(data.get("expires_at"))
        verified = self.call("/api/account/me", token=token, method="GET")
        account = verified.get("account")
        if not isinstance(account, dict) or not all(
            isinstance(account.get(k), str) and account[k]
            for k in ("id", "email", "full_name")
        ):
            raise LoginError(
                "Issued credential could not be verified. Cancel and restart /login."
            )
        if self.cancelled():
            raise LoginError(
                "Account authorization cancelled before persistence; remote revocation will be attempted."
            )
        try:
            with session_guard(self.store) as stream:
                if (
                    self.cancel_event.is_set()
                    or generation(self.store, stream) != self.generation
                ):
                    raise LoginError(
                        "Account authorization cancelled before persistence."
                    )
                self.store.save(
                    {
                        "access_token": token,
                        "expires_at": data["expires_at"],
                        "account": account,
                    }
                )
        except StorageError:
            raise LoginError(
                "Remote issuance succeeded but secure local storage failed. Existing credentials remain. Re-enter the code within 120 seconds to recover, or cancel to revoke and restart."
            ) from None
        self.account = account
        self.complete = True
        self.close()
        return "Wizard website account connected and verified. Runtime and provider configuration are unchanged."

    def close(self, cancel=False):
        if self._closed:
            return
        if cancel and self.rid and not self.complete:
            try:
                self.call("/api/cli/cancel", self.proof())
            except LoginError:
                pass  # Pending requests expire; unconfirmed issued credentials expire in 30 days.
        if self.rid and hasattr(self.store, "pending_store"):
            try:
                with session_guard(self.store):
                    pending = self.store.pending_store()
                    proofs = pending.load() or {}
                    proofs.pop(self.rid, None)
                    if proofs:
                        pending.save(proofs)
                    else:
                        pending.delete()
            except StorageError:
                pass  # Logout clears/cancels proofs left by an interrupted login.
        self.active = False
        if self._held_lock:
            self._held_lock = False
            self._lock.release()
        if self.owns_client:
            self.client.close()
        self._closed = True


def terminal_login(console):
    flow = None
    try:
        flow = LoginFlow()
        console.print(flow.start(), markup=False, soft_wrap=True)
        if flow.complete:
            return 0
        while flow.active:
            code = input("Website code (or /cancel-login): ").strip()
            if code == "/logout":
                from wizard.cli.account_logout import terminal_logout

                flow.cancel_event.set()
                return terminal_logout(console)
            if code in {"/cancel-login", "/exit"}:
                console.print("Account authorization cancelled.", markup=False)
                return 1
            try:
                console.print(flow.submit(code), markup=False)
                return 0
            except LoginError as exc:
                console.print(str(exc), markup=False)
                if flow.cancelled():
                    return 1
    except (EOFError, KeyboardInterrupt):
        console.print("Account authorization cancelled.", markup=False)
        return 1
    except (LoginError, StorageError) as exc:
        console.print(str(exc), markup=False)
        return 1
    finally:
        if flow:
            flow.close(cancel=not flow.complete)


class LoginWorker:
    """One background login conversation; the TUI retains its own event loop/input."""

    def __init__(self, notify):
        import queue

        self.notify = notify
        self.on_authenticated = None
        self.codes = queue.Queue(maxsize=1)
        self.stop = threading.Event()
        self.running = True
        self.thread = threading.Thread(
            target=self._run, name="account-login", daemon=True
        )

    def start(self):
        self.thread.start()

    def submit(self, value):
        import queue

        try:
            self.codes.put_nowait(value)
        except queue.Full:
            self.notify("An account code exchange is already queued. Please wait.")

    def cancel(self):
        self.stop.set()

    def _run(self):
        import queue

        flow = None
        try:
            flow = LoginFlow(cancel_event=self.stop)
            message = flow.start()
            if flow.complete and not flow.cancelled() and self.on_authenticated:
                self.on_authenticated(flow.account)
            self.notify(message)
            while not flow.cancelled() and flow.active:
                try:
                    code = self.codes.get(timeout=0.2)
                except queue.Empty:
                    if flow.expires_at and flow.expires_at <= datetime.now(UTC):
                        self.notify("Account authorization expired. Run /login again.")
                        break
                    continue
                try:
                    message = flow.submit(code)
                    if flow.complete and not flow.cancelled() and self.on_authenticated:
                        self.on_authenticated(flow.account)
                    self.notify(message)
                except LoginError as exc:
                    self.notify(
                        str(exc) + "\nEnter a fresh website code or /cancel-login."
                    )
        except (LoginError, StorageError) as exc:
            self.notify("Account login unavailable. " + str(exc))
        except Exception:  # noqa: BLE001 -- isolate platform browser/worker errors from secrets
            self.notify(
                "Account login failed. Existing account credentials were preserved."
            )
        finally:
            if flow:
                flow.close(cancel=not flow.complete)
            self.running = False
