# Verification record — account authorization implementation

Branch: `fix/runtime-verification-integration` (explicitly authorized by user).
Frontend inspected read-only on `wizar-web`; no frontend source changed.

## Focused verification

The final focused command is:

```powershell
$env:WIZARD_ACCOUNT_TEST_DATABASE_URL = 'postgresql://TEST_USER:TEST_PASSWORD@127.0.0.1:5432/TEST_DATABASE'
.\venv\Scripts\python.exe -m pytest backend/tests wizard/tests/test_account_login.py wizard/tests/test_tui_controls.py -q --tb=short --basetemp=output/pytest-account-NEW_UNIQUE_SUFFIX
```

The session supplied this test variable programmatically from the repository's
already configured, reachable local PostgreSQL URL without printing the URL or
credentials. Tests used only newly generated isolated schemas, asserted their
search path, applied migrations twice, and removed only those test schemas.
No application schema/data was migrated or reset.

Final focused result: **58 passed, 2 skipped**. A subsequent contract review
added explicit assertions for `request_id` in pending/approved responses; the
two affected real-PostgreSQL tests were rerun and both passed. Skips: native Windows Credential Manager
has no logon session in the sandbox; POSIX ownership/mode test requires a POSIX
host. Native Windows storage was separately run outside the sandbox using:

```powershell
.\venv\Scripts\python.exe -m pytest wizard/tests/test_account_login.py::test_windows_credential_manager_roundtrip_isolated_target -q --tb=short
```

Result: **1 passed**. It creates, replaces, reads, and deletes only a uniquely
named throwaway Credential Manager target. It does not replace a user's account
credential. The initial sandbox attempt failed with Windows error 1312; this
was not treated as successful persistence or worked around with plaintext storage.
POSIX test is added but has not run on a POSIX host.

Coverage includes real PostgreSQL migration repeatability/isolation, registration
and session rotation, password-login continuation, already authenticated users,
fixed server continuation ignoring arbitrary returnTo, unauthenticated/direct
API access, tampered browser context, CSRF and Origin denial, account binding,
verifier mismatch, code and request expiration at exact boundaries, invalid-code
counters/limits, initiation limits, duplicate approval, multiple requests, replay,
concurrent exchange (eight contenders, exactly one credential), browser/CLI
cancellation races, transactional rollback after forced insert failure, recovery
of a committed issuance, recovery expiry, credential expiry/revocation, retention
without deleting live credentials, logout independence, and malformed payloads.

OIDC tests use real signed RS256 ID tokens and a simulated provider over mocked
HTTP. They test nonce/audience/email verification, state replay, S256 PKCE exchange,
account creation/continuation, and refusal to auto-link a password account by email.
They DO NOT establish a real provider deployment or browser E2E.

`test_http_cli_postgres.py` starts an actual uvicorn server on a fresh loopback
socket, uses separate HTTP website/CLI clients, persists to real isolated
PostgreSQL, runs the actual LoginFlow exchange/account verification, and asserts
completion status. Its storage fixture is ephemeral; native storage is separately
tested above. No website UI is fabricated: backend `/cli/complete` returns 404.

CLI tests cover manual browser fallback, private verifier, invalid code, ambiguous
network/malformed response, separate recovery instead of replay, duplicate login,
secure-save failure preserving old credentials, recovery after save failure,
proof-bearing cancellation, EOF, cancellation during exchange before persistence,
active TUI investigation compatibility, and selectable `/login` menu rendering,
input focus, slash help and Tab completion.

## Quality/build checks

- `ruff check backend wizard/cli/account_login.py wizard/cli/account_storage.py wizard/tests/test_account_login.py`: passed.
- `ruff format --check` for those paths: passed.
- `python -m compileall -q backend wizard/cli/account_login.py wizard/cli/account_storage.py`: passed.
- `git diff --check -- pyproject.toml wizard/cli/main.py wizard/cli/parser/command_parser.py wizard/cli/tui/app.py`: passed.
- `python -m pip wheel --no-deps --no-build-isolation --wheel-dir output/account-auth-dist .`: passed; wheel inspected to contain backend and SQL migration.
- `python -m pip install --no-deps --no-build-isolation -e .`: passed in the existing project venv.
- `venv/Scripts/wizard.exe --help`: passed; advertises `/login`.
- `python -m wizard /login` without account URL: reports the required configuration, without starting runtime services or prompting for a password.

The first wheel attempt lacked setuptools in the existing venv. Installed the
project's declared setuptools/wheel build requirements, plus optional PyJWT crypto
and the dev Ruff tool, then rebuilt successfully. No new runtime dependency is
required except the already declared psycopg/FastAPI/httpx stack; OIDC is an
explicit optional extra. Pip emitted a version-check warning, unrelated to build.

Linting the three existing dispatcher modules also reports 11 existing findings
(Optional annotations, Typer argument defaults, unused frontend suggestion import,
and broad existing exception handlers). They are not refactored for this task.
The original planner tsconfig has pre-existing whitespace changes; scoped diff
checks exclude that unrelated work.

## Broader regression runs — not green

Ran `python -m pytest wizard/tests -q --tb=short` with a fresh workspace basetemp
outside the sandbox: **302 passed, 11 failed** (before the final extra EOF,
cancellation and menu-visibility cases were added). All 11 failures were then
reproduced outside the sandbox in a comparison copy restoring the original three
CLI dispatcher files from HEAD. The real working files were never reverted.
Failures concern existing explain frontend hints, Playwright-versus-agent-browser
discovery assumptions, frontend discovery UI, missing narration for browser tools,
usage dotenv forwarding and runtime interpreter selection. New login tests passed.

After the user's request to make `/login` visible in the TUI, ran account/TUI
controls plus all `test_tui_screens.py`: **170 passed, 2 skipped, 7 failed** in the
sandbox. The seven failures are the browser/discovery/narration cases above;
none involves the new selectable account action. The focused final run includes
the new menu action and passed.

Ran `python -m pytest wizard-runtime-engine/tests -q --tb=short` outside the
sandbox with a fresh workspace basetemp: **523 passed, 67 failed, 7 skipped**.
Runtime source was not edited by this task. Observed failures include undefined
`process_observations` in context packaging, legacy browser/CDP interfaces,
report/finalization signature expectations, lifecycle timing, and tool/planner
expectations. These remain unresolved. The complete runtime suite cannot be
claimed compatible/green from this run. The account backend is not imported or
mounted into that runtime app, and runtime/provider settings were not altered.

Initial broad sandbox runs failed fixtures because Windows denied access to the
shared default pytest temp directory. Those failures were rerun outside sandbox
with unique workspace temporary directories; the results above are the actual
completed runs. Existing Starlette/httpx deprecation and mixed-user pytest-cache
permission warnings were also observed. They were not hidden or turned into passes.

## Preservation and remaining integration

Final comparison of the original eight modified files still showed exactly
233 insertions/35 deletions across those same eight paths, matching the initial
inspection. The original two untracked runtime files were left untouched. New
changes are in `backend`, the two CLI account modules/test, pyproject packaging,
and the existing main/parser/TUI dispatcher only. No branch switch, reset, remote
change, commit, push, or deployment occurred.

No frontend build/lint/TypeScript checks were run: `wizardsite` is not in this
checkout and frontend files were not changed. Complete browser E2E, real OIDC
provider credentials/callback registration, production TLS/reverse proxy/database
roles and mail/reset delivery remain outstanding. Frontend's prior missing ESLint
setup/CSS warnings were read from its handoff, not re-verified in this checkout.
Use `FRONTEND_INTEGRATION_PROMPT.md` in the separate `wizar-web` session to finish
UI integration and run the actual browser flow. Backend/CLI protocol verification
must not be described as frontend/backend/database/CLI browser E2E completion.
