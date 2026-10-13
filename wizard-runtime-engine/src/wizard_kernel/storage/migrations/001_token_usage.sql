-- Additive, repeatable usage migration. No investigation/sandbox tables touched.
CREATE TABLE IF NOT EXISTS wizard_sessions (
    session_id text PRIMARY KEY,
    profile_id text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS wizard_sessions_profile_idx ON wizard_sessions(profile_id);
CREATE TABLE IF NOT EXISTS wizard_runs (
    run_id text PRIMARY KEY,
    session_id text NOT NULL REFERENCES wizard_sessions(session_id),
    command text NOT NULL CHECK (command IN ('investigate', 'verify', 'report', 'explain')),
    status text NOT NULL,
    started_at timestamptz NOT NULL,
    finished_at timestamptz,
    revision bigint NOT NULL DEFAULT 0,
    pending_requests integer NOT NULL DEFAULT 0 CHECK (pending_requests >= 0),
    incomplete boolean NOT NULL DEFAULT false
);
CREATE INDEX IF NOT EXISTS wizard_runs_session_started_idx ON wizard_runs(session_id, started_at DESC);
CREATE TABLE IF NOT EXISTS token_usage_events (
    event_id text PRIMARY KEY,
    run_id text NOT NULL REFERENCES wizard_runs(run_id),
    provider text NOT NULL,
    model text NOT NULL,
    agent text,
    provider_request_id text,
    input_tokens bigint CHECK (input_tokens >= 0),
    output_tokens bigint CHECK (output_tokens >= 0),
    total_tokens bigint CHECK (total_tokens >= 0),
    usage_source text NOT NULL CHECK (usage_source IN ('provider-reported', 'estimated', 'unavailable')),
    accuracy text NOT NULL CHECK (accuracy IN ('exact', 'provisional', 'incomplete')),
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS token_usage_run_created_idx ON token_usage_events(run_id, created_at);
CREATE UNIQUE INDEX IF NOT EXISTS token_usage_provider_request_idx
    ON token_usage_events(run_id, provider, model, provider_request_id)
    WHERE provider_request_id IS NOT NULL;
