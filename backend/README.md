# Wizard website account backend and CLI authorization

Implemented on `fix/runtime-verification-integration`, as explicitly authorized.
The frontend remains on `wizar-web`; it has NOT been merged, edited, or integrated.
This is a working backend/CLI protocol, not a claim of complete browser E2E.

## Discovery and boundaries

The destination contained no website identity backend, OAuth handlers, authoritative
account table, account credential store, or runtime-service authentication middleware.
`wizard_kernel.api.app` serves investigation/browser/usage routes; the agent service
serves agent routes. `storage/migrations/001_token_usage.sql` contains usage
`wizard_sessions`, `wizard_runs`, and `token_usage_events`. Those sessions/profile IDs
are local accounting identifiers, not verified website identities.

The user subsequently authorized a new `backend` directory. It is the new identity
authority: FastAPI and psycopg/PostgreSQL, matching the existing Python services.
No existing account schema has been duplicated. Nothing modifies runtime/provider
endpoints, tokens, model configuration, usage profile ownership, or provider keys.
CLI credentials authenticate ONLY the account API below. They do not secure or
configure the investigation runtime, and the account backend must not be deployed
as a proxy that publicly exposes the unauthenticated investigation service.

Read-only `git show wizar-web:...` inspection confirmed the supplied frontend evidence:
`/cli/authorize`, `/cli/connect`, and `/cli/complete` are previews. The existing
`.html` forms POST to `/login`, `/register`, `/forgot-password`; there is no existing
OAuth implementation to preserve. `returnTo=/cli/connect` is navigation, not identity.
The frontend needs the separate integration work in `FRONTEND_INTEGRATION_PROMPT.md`.

## Files

- `backend/app.py`: website session, CSRF, form handlers, CLI API, account verification/revocation.
- `backend/authorization.py`: state machine, PostgreSQL locking/issuance, limits and recovery.
- `backend/security.py`: random secrets, purpose-separated HMACs, digests, salted scrypt passwords.
- `backend/config.py`: separate account configuration, HTTPS/loopback validation.
- `backend/db.py`: bounded connection pool, explicit migration and retention commands.
- `backend/oidc.py`: optional configured OIDC provider, authorization-code flow, state/nonce/PKCE.
- `backend/migrations/001_account_authorization.sql`: repeatable additive account migration.
- `backend/tests/*`: security, real PostgreSQL, signed OIDC/provider simulation, loopback HTTP/CLI tests.
- `wizard/cli/account_login.py`: HTTP protocol, browser fallback, verified exchange, recovery,
  terminal interaction, and background TUI worker.
- `wizard/cli/account_storage.py`: Windows Credential Manager and private POSIX fallback.
- `wizard/cli/main.py`, `parser/command_parser.py`, `tui/app.py`: existing dispatcher/help integration.
- `wizard/tests/test_account_login.py`: CLI, TUI, EOF/network/storage and real Windows-store checks.
- Root `pyproject.toml`: package the backend/migration, optional OIDC dependency, include backend tests.

All eight previously modified tracked files and both previously untracked runtime
files are outside this implementation's edited paths. No branch switch, reset,
deployment or application-data migration was performed during implementation.
Commit/push is a separate step requiring explicit user authorization.

## Configuration and development startup

Use a dedicated development/test database or a separately scoped PostgreSQL role.
No root `.env` is implicitly loaded by this backend or by the CLI account client.
The existing runtime's `WIZARD_DATABASE_URL` is deliberately NOT an account fallback.
Set these in each relevant service's environment; examples contain placeholders only:

```powershell
# From repository root; use the existing venv or create your own.
.\venv\Scripts\python.exe -m pip install -e '.[dev,account-oauth]'
$env:WIZARD_ACCOUNT_DATABASE_URL = 'postgresql://ACCOUNT_USER:ACCOUNT_PASSWORD@127.0.0.1:5432/ACCOUNT_DATABASE'
$env:WIZARD_ACCOUNT_PUBLIC_ORIGIN = 'http://localhost:3000'
$env:WIZARD_ACCOUNT_LOCAL_DEV = '1'
# Generate once into a secret manager/environment, never check in or print in logs.
$env:WIZARD_ACCOUNT_SECRET = 'REPLACE_WITH_AT_LEAST_32_RANDOM_BYTES_FROM_A_SECRET_MANAGER'
.\venv\Scripts\python.exe -m backend.db
.\venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8090 --no-access-log
```

`WIZARD_ACCOUNT_SECRET` must be a strong random service secret of at least 32 bytes,
not the literal example. It must stay stable and identical across workers. Key
rotation invalidates pending codes/CSRF/recovery; existing bearer digests still
verify until expiry/revocation. Sessions are 256-bit opaque random cookie tokens.
Migration has a PostgreSQL advisory transaction lock and is repeatable. It creates
new tables only; no runtime migration or existing data is reset.

In the separate frontend checkout, configure a same-origin reverse proxy/Next
rewrite from `/api/auth/*`, `/api/cli/*`, `/api/account/*`, exact `/login`, `/register`,
`/forgot-password`, `/logout`, and `/oauth/oidc/*` to `http://127.0.0.1:8090`.
Keep `/login.html`, `/register.html`, `/forgot-password.html`, assets and `/cli/*`
served by Next. Start that checkout with its actual pnpm scripts, e.g. `pnpm dev`.
This proxy/UI change has NOT been made here. Until then the CLI can talk to the
backend directly with public origin/CLI URL both set to port 8090, but its browser
URL will correctly return 404 because this backend does not invent replacement pages.

In another terminal after frontend integration:

```powershell
$env:WIZARD_ACCOUNT_URL = 'http://localhost:3000'
$env:WIZARD_ACCOUNT_LOCAL_DEV = '1'
.\venv\Scripts\python.exe -m wizard
# Enter /login in the existing TUI, or use the same dispatcher directly:
.\venv\Scripts\python.exe -m wizard /login
```

The main TUI menu contains only investigate, verify, report and explain.
In the existing intent composer, type `/` to open the inline slash-command menu;
type `/log` to filter to `/login`. Up/Down highlight, Enter explicitly submits
the selected command through the existing handler, Tab fills without submitting,
and Escape dismisses without changing the draft or cancelling an active run.
Descriptions appear only in that popup; no persistent slash help footer remains.
The existing venv uses an editable installation, so restart a running TUI to load
these changes. From PowerShell:

```powershell
.\venv\Scripts\Activate.ps1
wizard
# Type / in the composer; from the primary menu, / focuses that same input.
```

No runtime/planner/LLM service is required for `wizard /login` standalone. Bare
`wizard` retains its existing service-supervision behavior; the new account worker
does not start the account backend. The TUI keeps responding to `/status`, menu
input and `/exit`; while login is pending, plain input is treated as the website
code. `/cancel-login` releases that input mode. Duplicate `/login` keeps the current
request. The process-wide guard prevents a second in-process conversation;
separate processes/terminals get independent requests.

Production requires HTTPS at the public origin and CLI URL, `LOCAL_DEV` unset,
trusted proxy forwarding of HTTPS only, no caching of auth/API responses, no
request-body/Authorization logging, and suppression of OAuth callback query logs
at the reverse proxy. `--no-access-log` suppresses uvicorn's callback query logging.
Do not trust arbitrary forwarded IP/protocol headers; configure uvicorn's trusted
proxy addresses narrowly. Rate limits use `request.client.host`, not a submitted
IP header. A proxy without trusted client forwarding shares its rate budget.
No CORS origins are enabled.

Optional OIDC configuration:

```powershell
$env:WIZARD_OIDC_ISSUER = 'https://YOUR_CONFIGURED_OIDC_ISSUER'
$env:WIZARD_OIDC_CLIENT_ID = 'YOUR_OIDC_CLIENT_ID'
$env:WIZARD_OIDC_CLIENT_SECRET = 'YOUR_OIDC_CLIENT_SECRET'
# Register this exact redirect with that provider:
# https://YOUR_WEBSITE_ORIGIN/oauth/oidc/callback
```

This is one configured OIDC provider supporting discovery, RS256 ID tokens,
PKCE S256, and verified email claims. It is not an assumed GitHub/Google OAuth
implementation. Password-account auto-linking by provider email is refused;
`oauth_account_link_required` requires signing into the existing password account.
Provider linking UI/API is not implemented. Provider secrets stay server-side.
The validation uses the OIDC state/nonce/issuer/audience rules from
[OIDC Core](https://openid.net/specs/openid-connect-core-1_0.html) and explicit
signature/claim verification through [PyJWT](https://pyjwt.readthedocs.io/en/latest/usage.html).
Real provider credentials and callback deployment have not been tested.

## Newly introduced API contract (v1 of this implementation)

All times are server-defined UTC ISO 8601 timestamps. Sensitive successes AND
errors use `Cache-Control: no-store`, `Pragma: no-cache`, `Referrer-Policy: no-referrer`.
API failures are JSON `{"error":"machine_readable_code"}`; no submitted proof,
password, code, bearer, database URL or account lookup detail is echoed. There is
no generic redirect parameter. No API accepts browser-supplied account identity.
Unknown routes (including direct backend `/cli/complete`) return 404.

The website and CLI use the SAME public origin. Browser fetches use same-origin
credentials. Session cookie is `__Host-wizard_site` (Secure, HttpOnly, SameSite=Lax,
Path=/, no Domain); explicitly configured loopback development uses `wizard_site`
without Secure. Cookies never contain pending IDs, codes or account claims.

### Website identity/session

| Method/path | Authentication, payload | Success |
|---|---|---|
| GET `/api/auth/context` | Existing cookie or new anonymous session | 200 `{"csrf":"HEX_HMAC","account":null or {"id":"UUID","email":"...","full_name":"..."},"cli_pending":true/false}`; sets cookie if new |
| POST `/login` | Session + Origin + CSRF; normal form `email,password,remember?` | 303 `/cli/connect` only for server-held pending continuation, otherwise `/`; rotates cookie |
| POST `/register` | Session + Origin + CSRF; existing fields `fullName,email,password,confirmPassword,acceptTerms` | 303 as above; creates account and authenticated session atomically; rotates cookie |
| POST `/forgot-password` | Session + Origin + CSRF; `email` | 503 `password_reset_delivery_unconfigured`; no fake delivery |
| POST `/logout` | Session + Origin + CSRF | 200 `{"signed_out":true}`; rotates to anonymous session, clears continuation, cancels pending/approved requests; issued CLI credentials remain independent |
| POST `/oauth/oidc/start` | Session + Origin + CSRF | 303 provider authorization URL with random state/nonce and S256 PKCE |
| GET `/oauth/oidc/callback` | Bound session cookie plus one-time state and provider code | Verified provider identity -> rotated authenticated cookie and 303 continuation; never a frontend completion callback |

For all browser POSTs, `Origin` must equal `WIZARD_ACCOUNT_PUBLIC_ORIGIN` EXACTLY.
Send CSRF from context as `X-CSRF-Token` for JSON or hidden form field `csrf` for
ordinary form POST. Form handlers accept `application/x-www-form-urlencoded` and
JSON. Fetch context again after login/logout/OIDC because session rotation changes
CSRF. Passwords use salted scrypt; registration requires 12–256 characters,
matching confirmation, accepted terms, valid normalized email and 1–200 character
name. Email/password sign-in is not email ownership verification; no mail service
exists. Add CSRF to ALL ordinary auth visits, even without a CLI hint.

Anonymous sessions last 12 hours; password/OIDC login sessions last 7 days or 30
days for a checked `remember`. Cookie token rotation preserves the server session
ID and pending association across login/registration/OIDC. The fixed return hint
is presentation only: submitted/query `returnTo` is ignored by the backend.

Auth errors: 400 `invalid_body`, `invalid_registration`, `body_too_large` (413),
401 `session_required`/`invalid_credentials`, 403 `origin_rejected`/`csrf_rejected`,
409 `already_authenticated`/`registration_unavailable`/`session_changed`, 429
`rate_limited`, 503 `service_unavailable`. OAuth additionally returns 503
`oauth_unconfigured`/`oauth_dependency_unavailable`/`oauth_configuration_invalid`,
403 `oauth_state_invalid`, 401 `oauth_verification_failed`, 409
`oauth_cancelled_or_session_changed`/`oauth_session_changed`/`oauth_account_link_required`.
Callback state is consumed before provider exchange, including failed exchanges;
restart OIDC after a provider/network failure. It cannot be replayed.

### Initiation and website authorization

| Method/path | Proof and payload | Success |
|---|---|---|
| POST `/api/cli/requests` | CLI only: no Origin; JSON `{"verifier_hash":"SHA256_HEX_OF_CLI_VERIFIER"}` | 201 `{"request_id":"UUID","expires_at":"ISO","authorization_url":"PUBLIC_ORIGIN/cli/authorize#request_id=UUID&ticket=OPAQUE"}` |
| POST `/api/cli/browser/bind` | Session + Origin + CSRF; `{"request_id":"UUID","ticket":"OPAQUE"}` from URL fragment | 200 `{"request_id":"UUID","continue_to":"/login.html?returnTo=%2Fcli%2Fconnect"}` or `/cli/connect` if already authenticated |
| GET `/api/cli/browser` | Bound, authenticated website session; no request/account parameter | 200 pending/approved/exchanged state below |
| POST `/api/cli/browser/approve` | Same session + Origin + CSRF; `{}`; explicit human approval | 200 approved state including real code and expiry |
| POST `/api/cli/browser/cancel` | Bound session + Origin + CSRF; `{}`; works before sign-in | 200 `{"state":"cancelled","request_id":"UUID"}` |

The CLI creates a 256-bit verifier locally and sends only its SHA256 challenge at
initiation. The verifier never appears in browser URLs, cookies, storage, or UI.
The separate 256-bit browser ticket is ONLY a first-session binding capability;
it cannot redeem or read a code without authentication. Its digest persists.
The fragment avoids HTTP access logs/referrers. On `/cli/authorize`, first fetch
context, read the fragment, POST bind, then remove it with `history.replaceState`
only after successful binding. On bind error show an actionable restart state;
never continue on a request ID alone. An already-bound session can reload later
pages using its server-held context without retaining the ticket in JS storage.
Reopening the original URL in another session is rejected, not reassigned.

Pending response: `{"state":"pending","request_id":"UUID","expires_at":"ISO"}`.
Approved adds `"code":"12_UPPERCASE_HEX_CHARACTERS"` and `"code_expires_at":"ISO"`.
Exchanged response: `{"state":"exchanged","request_id":"UUID","complete_to":"/cli/complete"}`.
GET never approves or generates a code. Repeated approval and reload return the
same code/expiry. Expired/locked codes are never silently reissued. Completion
must poll GET (e.g. every 2 seconds) and render actual success only for `exchanged`.
No direct `/cli/complete` visit, preview link, or client-side flag grants success.

A browser session selects its most recently bound request. Multiple terminals
have independent proofs; binding a later request does not cancel, reassign or
redeem an earlier one. Reopen the earlier terminal's original URL in that same
browser session to select it again. Display returned request ID and current
account confirmation to avoid confusing requests. Only one account can ever
be associated with an approved request. Session/account changes are checked
inside the approval transaction. No account association comes from the browser.

Errors include 401 `authentication_required`/`session_required`, 404
`missing_context`/`invalid_context`, 409 `context_already_bound`/`session_changed`/
`already_exchanged`, 403 `account_mismatch`, 410 `expired`/`code_expired`/`cancelled`/
`expired_or_cancelled`, 429 `attempt_limit`/`rate_limited`. Missing or malformed UUID
is 400 `invalid_request_id`; malformed ticket is 400 `invalid_context`. Browser
cancellation racing with exchange either wins and blocks issuance, or gets 409
`already_exchanged`; the UI must report that result rather than claiming cancellation.

### CLI exchange, recovery and account credential API

| Method/path | Proof and payload | Success |
|---|---|---|
| POST `/api/cli/exchange` | No Origin; JSON `{"request_id":"UUID","verifier":"CLI_SECRET","code":"DISPLAYED_CODE"}` | 200 `{"access_token":"wa_UUID.HEX_MAC","token_type":"Bearer","expires_at":"ISO"}` |
| POST `/api/cli/recover` | No Origin; JSON `{"request_id":"UUID","verifier":"CLI_SECRET"}` | Same credential, ONLY after committed exchange and for 120 seconds |
| POST `/api/cli/cancel` | No Origin; same proof JSON | 200 `{"state":"cancelled"}`; cancels unconsumed request, or revokes its credential if exchange already won |
| GET `/api/account/me` | `Authorization: Bearer ISSUED_CREDENTIAL` | 200 `{"account":{"id":"UUID","email":"...","full_name":"..."},"credential_expires_at":"ISO"}` |
| DELETE `/api/account/credential` | Same bearer | 200 `{"revoked":true}`; subsequent use returns 401 |

CLI operations reject browser Origin with 403 `cli_only`; cookie/request ID alone
is never accepted as CLI proof. API purpose is website account identification and
self-revocation only. CLI bearers are not accepted as website cookies. There is no
refresh token: credentials last 30 days; repeat `/login` to replace, explicitly
revoke using the bearer API to terminate early. Prior valid credentials are not
revoked or overwritten merely because a new login begins.

Exchange errors: 400 `invalid_code`/`invalid_body`/`invalid_request_id`, 403
`invalid_proof`, 409 `approval_required`/`already_exchanged`, 410
`expired_or_cancelled`/`code_expired`, 429 `attempt_limit`/`rate_limited`, 503
`service_unavailable`. Codes ignore spaces/hyphens and letter case. Recovery:
409 `not_exchanged`, 410 `recovery_expired`/`credential_unavailable`. Me/revoke:
401 `credential_required`/`credential_expired_or_revoked`.

## Lifecycle, transactions, limits, persistence

`pending -> approved -> exchanged`; pending/approved may become `cancelled`.
Proof-bearing CLI cancellation or bearer revocation can also change exchanged to
cancelled while preserving the exchange timestamp and revoking its credential;
website status then reports cancellation rather than a stale completion.
Expiry is derived, not a background transition. Pending request TTL: 600 seconds.
Code TTL: min(300 seconds after approval, remaining request lifetime). Equality
with expiration is expired. Code has 48 bits of HMAC-derived entropy (12 hex
characters), maximum five wrong codes per request, and still requires the separate
256-bit CLI verifier. Wrong-code counters are committed, not rolled back with
HTTP errors. Verifier mismatch cannot read account/code and is rate-limited.
The purpose-separated HMAC code is reproducible for authenticated page reloads;
only its digest and random nonce persist.

Initiation: 10/IP/minute. Other account API: 120/IP/minute aggregate. Login:
10/normalized-email/15 minutes. Registration: 5/normalized-email/hour. Approval:
10/session/minute. CLI proof operations: 30/request/minute, in addition to IP
limits. SQL atomic counters are shared by workers; failed requests count. 429
responses include `Retry-After: 60`; longer account windows may require waiting
up to their configured window. Limits are deliberately fixed in this version.
Request bodies are capped at 16 KiB. Database pool acquisition/connect timeout:
3 seconds; SQL statement timeout: 5 seconds. CLI network timeout: 8 seconds,
connect 3 seconds. No redirects, proxy environment inheritance, or blind exchange
retries in the account client.

Each exchange locks its `cli_authorizations` row `FOR UPDATE`, validates proof,
account association/state and expiration AFTER waiting for that lock, inserts
exactly one `account_cli_credentials` row and marks exchanged in the SAME
transaction. Unique authorization/credential relationship prevents double issuance.
A database failure rolls back both writes. Cancellation takes the same row lock.
Repeated initiation creates independent limited requests; duplicate in-process
CLI invocation is prevented locally. Repeated browser approval is idempotent;
repeated exchange is 409, never a second token or second issuance.

Response-loss policy: credential material is a purpose-separated HMAC of the
request ID and CLI verifier, prefixed `wa_`; only its SHA256 digest persists.
Proof-bearing `/recover` re-derives that exact credential for 120 seconds following
the committed exchange. It does not consume the code again or create credentials.
The CLI uses it after ambiguous failures/409; then verifies `/api/account/me`.
If recovery cannot establish the result, cancel/revoke and restart. If verification
or storage fails, re-entering the code triggers 409 -> recovery within that window.
After the window, cancel with the original in-memory proof and restart. The CLI
never saves that pending proof to disk. A disconnected/crashed client loses it;
an unconsumed request expires in ten minutes. If issuance already committed and
cancellation cannot reach the server, an inaccessible/orphaned credential expires
in 30 days. There is no claim that an unconfirmed cancellation revoked it.

The migration creates `website_accounts`, `website_sessions`, `cli_authorizations`,
`account_cli_credentials`, `account_rate_limits`, `website_oidc_attempts`, and
`website_oidc_identities`. Foreign keys bind sessions/requests/credentials/identities
to accounts; indexes cover expiry, session and account ownership; unique constraints
cover email, session/bearer/code digests, authorization issuance, OIDC issuer+subject.
OIDC state/nonce are digested; PKCE verifier is derived from service key and returned
state rather than stored plaintext. Passwords use fresh salted scrypt digests.

Schedule `python -m backend.db cleanup` daily against the account DB. It deletes
expired OIDC attempts/rate buckets, credentials expired/revoked for a day, terminal
or stale requests expired for a day only when no credential still references them,
and expired sessions only when no request references them. It never deletes live
credentials/accounts or resets usage data. Cleanup is explicit, not run on startup.

## Secure CLI storage

Windows uses the current user's native Credential Manager generic credential,
target `Wizard/account/<SHA256(public-origin)>`. Credential Manager protects the
blob; no plaintext fallback or file is used on Windows. Failure is reported,
including the case where a service/sandbox has no usable Windows logon session.

POSIX fallback is `~/.config/wizard/accounts/<SHA256(public-origin)>.json`, 0700 owned
directory, 0600 owned regular file, symlink rejection, same-directory temporary
file, fsync and atomic replace. Directory fsync is best effort after replacement
for filesystems that do not support it. This fallback is plaintext protected by
filesystem permissions, not a platform keychain, and was not exercised on Linux
in this Windows session. Directory/file validation failures fail closed. Native
Windows storage is tested with a unique throwaway target that is deleted afterward.

Storage is separate for each public origin and never inside a repository or
provider configuration. Tokens/verifiers are never command arguments, shell
history, ordinary terminal output, TUI history, or success messages. Browser URL
is intentionally displayed as the manual fallback and contains only the browser
ticket, never the CLI verifier or issued credential. Existing credentials survive
failed initiation, mistyped codes, network failures, or storage failure before
replacement. Success is printed only after account API verification AND storage.

## Reproduce verification and browser acceptance

Use a disposable TEST database URL in the test variable (never print it):

```powershell
$env:WIZARD_ACCOUNT_TEST_DATABASE_URL = 'postgresql://TEST_USER:TEST_PASSWORD@127.0.0.1:5432/TEST_DATABASE'
.\venv\Scripts\python.exe -m pytest backend/tests wizard/tests/test_account_login.py wizard/tests/test_tui_controls.py -q
.\venv\Scripts\python.exe -m pytest wizard/tests -q
.\venv\Scripts\python.exe -m pytest wizard-runtime-engine/tests -q
.\venv\Scripts\ruff.exe check backend wizard/cli/account_login.py wizard/cli/account_storage.py wizard/tests/test_account_login.py
.\venv\Scripts\ruff.exe format --check backend wizard/cli/account_login.py wizard/cli/account_storage.py wizard/tests/test_account_login.py
.\venv\Scripts\python.exe -m pip wheel --no-deps --no-build-isolation --wheel-dir output/account-auth-dist .
```

PostgreSQL tests create uniquely named `wizard_account_test_<random UUID hex>`
schemas, apply the migration twice, assert isolation, and drop ONLY their own test
schema afterward. They do not reset application tables. Tests skip if the explicit
test DB variable is absent. If pytest's default temporary path is inaccessible,
use `--basetemp=output/pytest-account-<NEW_UNIQUE_SUFFIX>` (pytest manages that path).
Windows Credential Manager's test skips with no sandbox logon session; run that
test from a normal user terminal to verify the native store.

After the frontend branch implements the integration prompt:

1. Start backend and proxied frontend as above. Run the actual `wizard /login` or
   type `/login` in the existing TUI. Verify the manual URL works if launch fails.
2. Continue via existing `/login.html` or `/register.html`, keep the fixed return
   hint through registration/reset navigation, and submit the original form plus
   hidden CSRF. Registration/password sign-in should redirect to `/cli/connect`.
   When OIDC is configured, start it by CSRF-protected POST and verify the same
   continuation after the real provider callback. Test cancellation at the provider.
3. Confirm account and request ID, explicitly approve, copy the real code, and enter
   it in that SAME terminal. CLI must verify `/api/account/me`, save securely, and
   print success. Website polling must observe exchanged before `/cli/complete`
   renders success. Repeat with an already authenticated website account.
4. Verify the SAVED credential without printing its token (from the CLI environment):

   ```powershell
   .\venv\Scripts\python.exe -c "from wizard.cli.account_login import account_origin,LoginFlow; from wizard.cli.account_storage import CredentialStore; f=LoginFlow(); c=CredentialStore(account_origin()).load(); print(f.call('/api/account/me',token=c['access_token'],method='GET')['account']); f.close()"
   ```

5. Test `/cli/connect` and `/cli/complete` directly with no session/request; neither
   should issue or assert success. Test tampered/missing ticket and alternate account.
   Test navigation to auth screens without a hint and with an unallowlisted hint.
6. Leave an approved code for five minutes, then try it (410); pending URL after ten
   minutes also expires. Try wrong codes five times (429). A second exchange of a
   consumed code is 409; secure recovery can return only the same credential for
   120 seconds. Controlled-time tests cover exact boundaries without waiting.
7. Cancel from website before/after sign-in and from terminal with `/cancel-login`,
   EOF, or interrupt. Retry old code: 410. Race cancellation and exchange; inspect
   the actual response instead of assuming navigation cancelled anything.
8. Test multiple terminals, page reload, transient API/database outage, lost exchange
   response, native-store failure, and recovery/restart. Run the frontend's pnpm
   build/lint plus explicit `pnpm exec tsc --noEmit`; build alone ignores type/lint
   failures. Existing frontend lint setup/CSS warnings must be reported separately.

See `VERIFICATION.md` for the exact results from this implementation session.
Remaining external dependencies: separate frontend integration/same-origin proxy,
production TLS/secrets/database role, real OIDC provider configuration, and a future
password-reset mail/delivery implementation. No complete browser E2E is claimed.
