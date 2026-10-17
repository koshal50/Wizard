# Copy-ready prompt for the Codex session on wizar-web

You are implementing frontend integration on `wizar-web`. The actual Python
account backend and Wizard CLI `/login` have now been implemented in the separate
`fix/runtime-verification-integration` checkout. Do not switch branches, overwrite
work, copy backend source into this frontend branch, create a second identity
system, or rebuild the existing auth/CLI screens. Inspect branch/status/guidance
before editing. Preserve styling, navigation, existing forms and `.html` URLs.

The backend contract is in `backend/README.md` in the backend checkout (original
workspace: `D:\all projects\Wizard`). Those changes may still be uncommitted, so
`git show` will not expose them until they are committed by the owner. Read that
file directly if accessible, otherwise use the exact contract below. Do not
assume that reading another branch integrates its code.

Backend discovery found no website identity provider or account schema; the user
explicitly authorized a new `backend` directory. It now owns PostgreSQL website
accounts, opaque cookie sessions, password login/registration, optional configured
OIDC, CLI authorization and revocable CLI account credentials. It does not
configure or authenticate the investigation runtime or any LLM provider.

## Required deployment seam

Configure a SAME-ORIGIN proxy/Next rewrite for `/api/auth/*`, `/api/cli/*`,
`/api/account/*`, exact `/login`, `/register`, `/forgot-password`, `/logout`, and
`/oauth/oidc/*` to the separately running account service (development backend
usually `http://127.0.0.1:8090`). Read the actual Next config before editing.
Keep `/login.html`, `/register.html`, `/forgot-password.html`, public assets, and
`/cli/*` served by the existing Next app. The backend must have
`WIZARD_ACCOUNT_PUBLIC_ORIGIN` set to the FRONTEND origin, e.g.
`http://localhost:3000`, with `WIZARD_ACCOUNT_LOCAL_DEV=1` only for loopback HTTP.
The CLI uses that same origin as `WIZARD_ACCOUNT_URL`. Production requires HTTPS
and host-only Secure cookies. Never proxy the unauthenticated investigation runtime
as if the account credential protected it. Never expose server secrets via
`NEXT_PUBLIC_*` or log authorization bodies, bearer headers, or callback queries.

## Exact browser contract

All sensitive responses are non-cacheable JSON. Use `cache: 'no-store'` for
fetches and `credentials: 'same-origin'`; never cache codes, sessions, or account
results in Next caches, service workers, localStorage, or static pages.

1. `GET /api/auth/context` -> 200:
   `{"csrf":"HEX_HMAC","account":null or {"id":"UUID","email":"...","full_name":"..."},"cli_pending":true/false}`.
   It creates an anonymous HttpOnly session cookie if absent. Production cookie
   is `__Host-wizard_site`, dev is `wizard_site`; JS must never access it.
   All browser POSTs require exact matching Origin (browser sends it) plus CSRF
   from context as `X-CSRF-Token` or normal form hidden field `csrf`. Refresh
   context after login/logout/OIDC because successful auth rotates cookie/CSRF.
2. CLI opens `/cli/authorize#request_id=UUID&ticket=OPAQUE`. On the existing page,
   fetch context and POST `/api/cli/browser/bind` with JSON
   `{"request_id":"UUID","ticket":"OPAQUE"}` plus CSRF. The 256-bit ticket
   binds the first browser session, not an account. It is distinct from the
   CLI-held verifier and is not a bearer credential. Only after successful bind,
   remove the fragment with `history.replaceState`. Do not propagate the ticket
   in links, query parameters, form fields, telemetry or persistent JS storage.
   Response: `{"request_id":"UUID","continue_to":"/login.html?returnTo=%2Fcli%2Fconnect"}`
   or `continue_to:"/cli/connect"` for an already authenticated session. Continue
   only to those allowlisted destinations. The backend retains pending context
   in its anonymous session across navigation and subsequent auth.
   Reload after fragment removal can use context (`cli_pending`) and current
   account for the same continuation. Missing both ticket and pending session
   means show restart instructions, not a fake login/authorization state.
3. Preserve normal `/login.html`, `/register.html`, `/forgot-password.html`
   navigation and their fixed `returnTo=/cli/connect` hint behavior; remove the
   preview shortcut/notice. Add CSRF to forms on ALL visits, including ordinary
   auth visits with no CLI hint. Existing `/login` form fields remain
   `email,password,remember?`; registration remains
   `fullName,email,password,confirmPassword,acceptTerms`. Register passwords must
   now be 12–256 characters, confirmation equal, terms accepted, name 1–200.
   Existing POST endpoints accept URL-encoded forms or JSON and return 303 to
   `/cli/connect` only for a real server-held pending request, otherwise `/`.
   The backend IGNORES arbitrary `returnTo`, account ID, or email as continuation
   proof. Do not invent a client-side auth token or mark sign-in successful from
   a hint. Handle JSON error responses within the original styled auth screens;
   keep original validation/password controls and field names. If adding fetch
   submission for styled errors, allow 303 to follow, verify the final URL is
   the same origin with path `/` or `/cli/connect`, and navigate only after the
   successful server response. The destination must still check real session.
   Prevent duplicate submission and preserve accessible error/focus behavior.
   `/forgot-password` currently returns 503
   `password_reset_delivery_unconfigured`; show truthful unavailability, not
   "email sent". No email delivery exists yet.
4. Optional configured OIDC uses CSRF-protected native POST
   `/oauth/oidc/start` (top-level form redirect), then backend
   GET `/oauth/oidc/callback?state=...&code=...`. Provider config is server-side;
   do not assume Google/GitHub. Show an OIDC affordance only when deployment has
   configured that provider. State/nonce/S256 PKCE are owned and verified by the
   backend; do not add a frontend callback, replace state, or pass a return URL
   through the provider. Successful callback rotates the cookie and resumes the
   same pending request. 503 `oauth_unconfigured`/`oauth_dependency_unavailable`
   must not be treated as successful OAuth. 409 `oauth_account_link_required`
   means use the existing password account; no automatic email-based linking.
5. On existing `/cli/connect`, GET `/api/cli/browser`. Without a bound
   authenticated website session it returns 401/404; offer allowlisted sign-in
   or restart guidance as appropriate, never generate a code client-side.
   `{"state":"pending","request_id":"UUID","expires_at":"ISO"}` means
   show account confirmation from context and an EXPLICIT Authorize action.
   POST `/api/cli/browser/approve` with `{}` plus CSRF. It returns
   `{"state":"approved","request_id":"UUID","expires_at":"ISO","code":"12_UPPERCASE_HEX","code_expires_at":"ISO"}`.
   Reuse `CliCodePlaceholder` presentation for real state, add actual copy
   action and terminal-entry instructions; handle clipboard denial by allowing
   selection. GET status returns the same approved code/expiry on reload.
   Never approve automatically on a GET, account login, or page mount.
   Countdown derives from server expiration but server status is authoritative.
   Request lasts ten minutes, code lasts at most five; expired code is not
   reissued on approval/reload. Give fresh-CLI `/login` restart instructions.
6. Poll GET `/api/cli/browser` every ~2 seconds only while needed, with cleanup,
   bounded retry/backoff and tab/request guards. Success is ONLY
   `{"state":"exchanged","request_id":"UUID","complete_to":"/cli/complete"}`.
   Navigate to `/cli/complete` only after that. The complete page must fetch
   backend status itself and gate `CliCompletionPreview` on confirmed exchanged;
   direct visits or client state must never assert a connected account. Backend
   cancellation/revocation subsequently returns 410. No preview shortcuts.
   Avoid showing stale results after switching to a different request.
7. Cancel buttons must POST `/api/cli/browser/cancel` with `{}` and CSRF before
   navigation. It works with the bound anonymous session too, so cancellation
   before login is real. Success is
   `{"state":"cancelled","request_id":"UUID"}`. On failure display the
   actual cancellation outcome. A 409 `already_exchanged` means exchange won
   the race; never display cancellation as successful. CLI cancellation uses
   its own strong proof and can revoke an exchange that already committed.
8. Multiple terminals are independent; the website session selects its most
   recently bound request. Display current account and returned request ID.
   Reopening an earlier terminal's original URL in the SAME session selects
   that request again; another browser session gets 409, not reassignment.

API failures: `{"error":"machine_readable_code"}`. Use actionable messages without
revealing secrets. 400 malformed fields/IDs, 401 session/auth required, 403
origin/CSRF/account mismatch, 404 missing/invalid context, 409 context already
bound/session changed/already exchanged, 410 expired/code_expired/cancelled,
429 attempt_limit/rate_limited (`Retry-After:60`), 503 service/database unavailable.
Do not treat a temporary network failure as proof of cancellation or completion.
The backend has no CORS allowance; make all calls through the same-origin proxy.

Frontend must NEVER call CLI-only `/api/cli/requests`, `/api/cli/exchange`,
`/api/cli/recover`, or `/api/cli/cancel`, and must never ask for, persist or expose
CLI verifier/access token. The actual CLI implements initiation, manual browser
fallback, code entry, proof-bearing exchange/recovery, account verification and
native storage. It prints success only after `/api/account/me` verifies the token
AND secure persistence succeeds. Windows uses Credential Manager. Tokens last
30 days and authorize only account API, not provider or runtime access.

## Verification and delivery

Implement the UI integration, do not stop at another plan/handoff. Preserve the
existing design/components/routes. Inspect package.json and use the actual pnpm
convention. Add browser/integration tests for login/register continuations, already
signed-in users, auth screen hint navigation, normal auth visits, missing/tampered
context, CSRF, cancellation, direct connect/complete guards, expiry/reload,
network/database errors, copy fallback, duplicate approval, multiple terminals,
and backend-confirmed completion. Exercise real OIDC only if configured; report
missing credentials accurately. Backend signed-provider simulation does not prove
real provider deployment.

Run explicit `pnpm exec tsc --noEmit` and `pnpm build`; Next build ignores type and
ESLint errors. Run `pnpm lint`, reporting the known missing ESLint setup rather
than bypassing it silently. Separate existing globals.css warnings from changes.
Run the actual backend + PostgreSQL + CLI + frontend browser sequence: migrate
a development account DB, start account service and same-origin frontend, run
Wizard and `/login`, authenticate/register, explicitly approve, copy code into
that terminal, verify saved account credential, and observe gated completion.
Exercise expiry, replay and both cancellation paths. Report exact tests run,
remaining failures/configuration, and changed frontend files. Claim browser E2E
only for a complete integrated run that actually passed. Do not commit, push,
deploy, or switch branches without user authorization.
