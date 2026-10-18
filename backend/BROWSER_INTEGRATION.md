# Live browser integration in separate worktrees

Open `Wizard.code-workspace` in VS Code. The backend/CLI stays on
`fix/runtime-verification-integration` in `D:\all projects\Wizard`; the website
stays on `wizar-web` in `D:\all projects\Wizard-web`. No branch merge is needed.
The frontend's `wizardsite/CLI_AUTH_INTEGRATION.md` supersedes its earlier preview
documentation. The backend's existing README remains authoritative for the API.

All browser and CLI traffic uses `http://localhost:3000`. Next proxies account
requests to `http://127.0.0.1:8090`, preserving session cookies and CSRF/Origin checks.
The backend's public origin must also be `http://localhost:3000`.

Terminal 1:

```powershell
cd 'D:\all projects\Wizard'
powershell -NoProfile -ExecutionPolicy Bypass -File .\backend\scripts\start-local-account-backend.ps1 -PublicOrigin http://localhost:3000
```

The launcher uses the existing Windows-encrypted, Git-ignored configuration in
`.secrets/wizard-account-local.clixml`, containing the dedicated account DSN and
stable service secret. PostgreSQL must be running. It verifies the existing seven
account tables without loading runtime configuration. The encrypted file is bound
to its Windows user/machine; use README's explicit environment setup on another
machine. No schema or authentication-persistence change was required.

Terminal 2:

```powershell
cd 'D:\all projects\Wizard-web\wizardsite'
corepack pnpm@9.15.9 dev --hostname localhost --port 3000
```

Terminal 3:

```powershell
cd 'D:\all projects\Wizard'
$env:WIZARD_ACCOUNT_URL = 'http://localhost:3000'
$env:WIZARD_ACCOUNT_LOCAL_DEV = '1'
.\venv\Scripts\wizard.exe /login
```

Use the actual website, not the simulator. Review the account and explicitly
approve, then paste the code into the original terminal. Website completion is
shown only after backend-confirmed exchange; CLI success additionally requires
account verification and secure persistence in Windows Credential Manager.

Headless Edge tests launch the actual executable and verify this flow. They
restore any existing saved localhost:3000 credential, revoke only their issued
test credentials, and leave uniquely named development test accounts in the
account database. They never reset user data. Browser traces/videos/screenshots
are disabled and output artifacts are ignored. A small CLI output fix prevents
Rich from line-wrapping the manual authorization URL; a regression test covers it.

For simulator-only testing, explicitly use `-PublicOrigin http://localhost:8090`
instead. Do not mix public origins. Production still requires HTTPS, managed
secrets, proper database roles and trusted proxy configuration. Real third-party
OAuth credentials and password-reset email delivery remain unconfigured/untested.
