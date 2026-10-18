# Live CLI account authorization

This branch now connects the existing UI to the backend in the separate
`fix/runtime-verification-integration` worktree. No branch merge is required.
`CLI_AUTH_UI.md` describes the earlier preview and is superseded by this document.

## Local configuration and startup

Open `D:\all projects\Wizard\Wizard.code-workspace` in VS Code. It contains the
backend/CLI folder and this website folder. Keep edits in their respective worktrees.

The backend's account database and stable service secret are encrypted with Windows
DPAPI in `Wizard/.secrets/wizard-account-local.clixml`, excluded from Git and bound
to the Windows user/machine. That file is already prepared on this machine. It is
not transferable to another developer. PostgreSQL must remain running.

Terminal 1 (backend):
```powershell
cd 'D:\all projects\Wizard'
powershell -NoProfile -ExecutionPolicy Bypass -File .\backend\scripts\start-local-account-backend.ps1 -PublicOrigin http://localhost:3000
```

For a fresh backend setup, use the backend README: set the explicit account DSN,
strong service secret, public origin `http://localhost:3000`, local-development
flag `1`, run `python -m backend.db` and `python -m backend.db check`, then
`python -m uvicorn backend.app:app --host 127.0.0.1 --port 8090 --no-access-log`.
Do not use the runtime database as a fallback. Never check in actual configuration.

Terminal 2 (frontend):
```powershell
cd 'D:\all projects\Wizard-web\wizardsite'
Copy-Item .env.example .env.local # only if .env.local does not already exist
corepack pnpm@9.15.9 install --frozen-lockfile
corepack pnpm@9.15.9 dev --hostname localhost --port 3000
```

`.env.local` contains only server-side proxy configuration:
```dotenv
WIZARD_ACCOUNT_BACKEND_URL=http://127.0.0.1:8090
WIZARD_ACCOUNT_LOCAL_DEV=1
```
It is ignored by Git. The flag explicitly permits loopback HTTP. Otherwise an HTTPS
backend origin is required. Restart Next after changing configuration. The browser
and CLI use localhost:3000; only the proxy uses 127.0.0.1:8090. Do not mix localhost
and 127.0.0.1 in browser URLs: sessions and Origin checks must stay consistent.

Terminal 3 (actual CLI; no simulator):
```powershell
cd 'D:\all projects\Wizard'
$env:WIZARD_ACCOUNT_URL = 'http://localhost:3000'
$env:WIZARD_ACCOUNT_LOCAL_DEV = '1'
.\venv\Scripts\wizard.exe /login
```

Open the complete printed URL, Continue to sign in, then sign in or use Create one.
Review the account/request on /cli/connect and explicitly authorize. Copy the real
12-character hexadecimal code into the original terminal. The page waits for the
backend's exchanged state before showing completion. The CLI independently verifies
the issued bearer with /api/account/me and saves it in Windows Credential Manager.

## Implemented contract and security

- Next proxies /api/auth/*, /api/cli/*, /api/account/*, exact POST auth paths /login,
  /register, /forgot-password, /logout, and /oauth/oidc/* to the account backend.
  The .html screens and /cli/* pages remain frontend routes. Cookies and backend
  redirects are preserved; no CORS relaxation or parallel identity system exists.
- GET /api/auth/context establishes/reads the HttpOnly website session and returns
  csrf, account or null, and cli_pending. Browser mutations send the fresh CSRF
  in X-CSRF-Token (forms also send csrf) with the browser's same-origin Origin.
- /cli/authorize reads only request_id and ticket from the CLI URL fragment.
  POST /api/cli/browser/bind associates the website session. The fragment is removed
  after confirmed binding; no verifier, ticket, code, bearer or account identity is
  stored in localStorage/sessionStorage. The CLI verifier stays private to the CLI.
- The fixed returnTo=/cli/connect hint survives links between existing auth screens;
  arbitrary return hints are ignored. Actual continuation lives in the backend
  session across login/register and configured OIDC redirects.
- Existing auth forms submit their established URL-encoded fields through fetch,
  obtain fresh CSRF, preserve cookie rotation with manual redirect handling, re-read the verified
  session after authentication, navigate only to /cli/connect or / based on that
  server-held context, and show errors without discarding the UI. Destination HTML
  compilation never holds an authentication POST open.
- GET /api/cli/browser reads pending, approved or exchanged state. Direct connect
  or complete visits without bound authenticated context cannot mint codes or show
  success. GET never approves. POST /api/cli/browser/approve requires explicit approval.
- Approval is idempotent: reload shows the same code/expiry. The frontend polls every
  two seconds, backs off transient/rate-limit failures, uses bounded fetch timeouts,
  and stops showing an expired code. The backend enforces all actual expiry/replay
  rules. Pending requests last 600 seconds; codes last at most 300 seconds and never
  outlive their request. Restart /login after expiry.
- POST /api/cli/browser/cancel works before and after sign-in. The UI reports
  cancellation only after confirmed cancelled state. An exchange race or network
  failure is not described as cancelled. /cancel-login remains available in the CLI.
- /cli/complete renders success only after GET reports exchanged. It tells the user
  to check the terminal for independent verification/storage success.
- Sensitive routes have no-store and no-referrer headers. Codes/tickets/passwords
  are not logged by frontend code; browser test artifacts are ignored and traces,
  videos and screenshots are disabled. Do not commit test artifacts or local secrets.
- CLI credentials identify a website account only; runtime/provider credentials
  and investigation behavior remain independent and unchanged.

The exact error/status and transactional contract remains documented in
`Wizard/backend/README.md`. No endpoint or PostgreSQL schema change was needed.

## Verification

```powershell
# Frontend worktree, with the backend and Next dev server running:
corepack pnpm@9.15.9 typecheck
corepack pnpm@9.15.9 exec next lint --file components/cli-flow.tsx --file components/cli-authorization.tsx --file app/cli/authorize/page.tsx --file app/cli/connect/page.tsx --file app/cli/complete/page.tsx
corepack pnpm@9.15.9 test:browser
# Stop Next dev before building (both use .next):
corepack pnpm@9.15.9 build
```

Browser tests require installed Microsoft Edge, the sibling backend worktree/venv,
and the actual wizard.exe. Set WIZARD_BACKEND_WORKTREE if the backend is elsewhere.
Run from a normal Windows logon with Credential Manager access, not an isolated
sandbox logon. Tests back up and restore the existing account credential for
localhost:3000, revoke only their issued test credentials, and cancel their pending
requests. They create uniquely named disposable development accounts and do not
reset the database. The OS browser-launch action is replaced by a test-only no-op;
the actual executable, dispatcher, verifier, exchange, verification and storage run
unchanged. Tests open the emitted URL in a real isolated headless Edge browser.

Expiry UI coverage advances browser time only; real server expiry, replay,
transaction/concurrency, rollback, response-loss and cancellation races are covered
by the backend's PostgreSQL suite. No live third-party OIDC credentials or email
reset delivery are configured. No provider OAuth or password-reset success is claimed.

## Results on this Windows checkout (2026-10-18)

- Actual wizard.exe + headless Microsoft Edge + Next + backend + PostgreSQL:
  6 browser tests passed (44.1 seconds), with no PowerShell simulator involved.
  Covers registration, rejected/correct sign-in, authenticated continuation,
  explicit approval, code reload, exchange, saved-credential verification,
  completion, client expiry UI, cancellation, direct/tampered visits, fixed
  navigation hints, ignored arbitrary return URLs, and ordinary website sign-in.
- Backend/CLI regression command:
  `python -m pytest backend/tests wizard/tests/test_account_login.py -q --disable-warnings`
  with WIZARD_ACCOUNT_TEST_DATABASE_URL configured internally for isolated schemas:
  64 passed, 1 skipped (POSIX file-mode test on Windows), 2 warnings.
  Newly added narrow-output URL regression separately: 1 passed.
- Explicit frontend typecheck passes. The script disables incremental caching
  because Next dev/build switches invalidate generated .next type files.
- Changed-component ESLint passes. Full `pnpm lint` remains blocked by existing
  unescaped apostrophes at components/hero.tsx:672 and :677, with existing warnings
  in unrelated UI components. Those files were not changed.
- `pnpm build` passed, generating all 11 static pages. Its existing settings skip
  TypeScript/ESLint, which were checked separately. Build warned about stale
  Browserslist data.
- Both worktree diffs were checked; local configuration and browser artifacts
  remain ignored. No commit, push, branch switch or merge was performed.
