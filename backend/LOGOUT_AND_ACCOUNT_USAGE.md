# CLI logout and account usage

Run `wizard /logout`, or enter `/logout` in the TUI (including while a login
is pending). There is no confirmation. The command removes only the current
origin's CLI credential and cancels pending CLI authorizations. It never calls
the website's `/logout` endpoint and leaves the browser signed in.

Successful removal immediately resets the TUI label to `(default user)`.
Messages are:

- `Youve been logged out of Wizard.`
- `Youre already logged out.`
- `Logged out locally. Could not revoke the server credential.`

Secure-storage failures produce `Logout failed. ...` and a nonzero standalone
exit status. A failure to remove a credential never produces a completion
message. Local removal happens before network revocation, so offline logout
does not retain a usable local credential. Offline server credentials may
remain valid until expiration; the command reports that revocation was not
confirmed.

Login persistence and logout removal share an OS file lock. A non-secret,
persisted generation identifier invalidates login work across CLI processes.
Pending request/verifier proofs are kept separately in the platform's secure
credential store, allowing standalone logout to cancel a pending TUI or terminal
authorization. TUI callbacks also use an operation identifier and a lock, so
stale login, identity, or status results cannot overwrite logout state.

The next `/login` creates a new request and code. Signed-in browser users see
`Continue as [account]` and `Use a different account`. Continuing still requires
explicit approval and terminal code entry. The new CSRF-protected
`POST /api/cli/browser/change-account` endpoint rotates the browser session to
an anonymous session, invalidates any prior approval/code, and preserves only
the pending CLI continuation for sign-in or registration. Ordinary CLI logout
does not change that browser session.

## Usage ownership

The runtime verifies CLI bearer credentials through the configured account
service's `/api/account/me`; it never trusts a submitted account ID. New runs
persist that permanent account UUID in investigation metadata. Existing usage
tables are reused: `wizard_sessions.profile_id = account:<permanent UUID>` is
the account ownership key, and usage events join it through their run/session.
Account-scoped session keys prevent a reused CLI session ID from mixing owners.
No database schema change or production data migration is needed for this
namespace. Both the existing account and usage schemas must already be installed.

`/status`, run usage, and usage SSE use the verified account's scope. The CLI
captures each run's authorization for its usage stream, while a new `/status`
reads the current secure credential. A run that continues after logout or
account switching retains its original owner. Authentication operations do not
modify usage rows, investigation history, project settings, or providers.

Anonymous legacy records retain their original local-profile ownership. They
are preserved and are not automatically assigned to an account because they
contain no trustworthy account identity. New accounts therefore do not inherit
another local user's anonymous usage. Existing account totals are aggregated
from saved events across credentials and sessions; no login operation resets
them. Account verification failure rejects authenticated requests instead of
silently attributing their usage to the anonymous profile.

## Verification

`backend/tests/test_logout_usage_postgres.py` uses generated isolated schemas,
real registration/approval/exchange/revocation, actual runtime request
authentication, and fixture provider usage through the existing usage spool.
It verifies zero initial usage, same-account accumulation across logout/login,
separate account totals, foreign-run rejection, browser-session retention,
fresh codes, account switching, and a new store reading persisted totals.

CLI tests cover offline and malformed revocation responses, secure deletion
failure, repeated logout, OS generation locking across processes, pending and
in-flight authorization races, stale identity callbacks, completion, and label
updates. Native Windows tests create and remove only unique throwaway targets.
POSIX permission tests require a POSIX host.

The website worktree includes `tests/browser/logout.spec.ts`, exercising actual
`wizard.exe` login/logout, fresh explicit approvals, account switching, browser
session retention, and cross-process pending cancellation in Edge. It backs up
and restores the existing CLI credential, revokes only its test credentials,
and uses uniquely named test accounts. Browser traces and videos remain disabled.

Validation results: the combined native-Windows/PostgreSQL run passed 157 tests
with one POSIX-only skip. Additional restoration, ownership, UI race, and
account-switch footer checks passed. All seven website browser regressions and
the website TypeScript check passed. Targeted lint, formatting, compilation,
and diff checks passed.

A broader usage-unit run still finds two unchanged supervisor-test failures:
`test_database_dotenv_value_is_passed_only_to_runtime` and
`test_supervisor_selects_separate_runtime_venv`. Those tests assert older service
configuration/interpreter-selection behavior; the supervisor was not modified
by this change. This is not a claim that the repository-wide suite is green.
