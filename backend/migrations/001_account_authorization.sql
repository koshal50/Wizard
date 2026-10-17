-- New website identity authority. Usage wizard_sessions are unrelated.
CREATE TABLE IF NOT EXISTS website_accounts (
    id uuid PRIMARY KEY,
    email text NOT NULL UNIQUE,
    full_name text NOT NULL,
    password_hash text,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS website_sessions (
    id uuid PRIMARY KEY,
    token_hash text NOT NULL UNIQUE,
    account_id uuid REFERENCES website_accounts(id) ON DELETE CASCADE,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS website_sessions_expiry ON website_sessions(expires_at);
CREATE TABLE IF NOT EXISTS cli_authorizations (
    id uuid PRIMARY KEY,
    verifier_hash text NOT NULL,
    ticket_hash text NOT NULL,
    browser_session_id uuid REFERENCES website_sessions(id) ON DELETE CASCADE,
    account_id uuid REFERENCES website_accounts(id) ON DELETE CASCADE,
    state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','approved','exchanged','cancelled')),
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    code_nonce text,
    code_hash text UNIQUE,
    code_expires_at timestamptz,
    attempts integer NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 5),
    exchanged_at timestamptz,
    CHECK(state NOT IN ('approved','exchanged') OR
        (account_id IS NOT NULL AND browser_session_id IS NOT NULL AND code_hash IS NOT NULL)),
    CHECK(state <> 'exchanged' OR exchanged_at IS NOT NULL),
    CHECK(exchanged_at IS NULL OR state IN ('exchanged','cancelled'))
);
CREATE INDEX IF NOT EXISTS cli_authorizations_expiry ON cli_authorizations(expires_at);
CREATE INDEX IF NOT EXISTS cli_authorizations_session ON cli_authorizations(browser_session_id);
CREATE TABLE IF NOT EXISTS account_cli_credentials (
    id uuid PRIMARY KEY,
    authorization_id uuid NOT NULL UNIQUE REFERENCES cli_authorizations(id) ON DELETE CASCADE,
    account_id uuid NOT NULL REFERENCES website_accounts(id) ON DELETE CASCADE,
    token_hash text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz
);
CREATE INDEX IF NOT EXISTS account_cli_credentials_account ON account_cli_credentials(account_id);
CREATE INDEX IF NOT EXISTS account_cli_credentials_expiry ON account_cli_credentials(expires_at);
CREATE TABLE IF NOT EXISTS account_rate_limits (
    bucket text PRIMARY KEY,
    starts_at timestamptz NOT NULL,
    hits integer NOT NULL
);
ALTER TABLE website_sessions ADD COLUMN IF NOT EXISTS pending_authorization uuid;
CREATE TABLE IF NOT EXISTS website_oidc_attempts (
    state_hash text PRIMARY KEY,
    session_id uuid NOT NULL REFERENCES website_sessions(id) ON DELETE CASCADE,
    nonce_hash text NOT NULL,
    expires_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS website_oidc_expiry ON website_oidc_attempts(expires_at);
CREATE TABLE IF NOT EXISTS website_oidc_identities (
    issuer text NOT NULL,
    subject text NOT NULL,
    account_id uuid NOT NULL REFERENCES website_accounts(id) ON DELETE CASCADE,
    PRIMARY KEY (issuer, subject)
);
