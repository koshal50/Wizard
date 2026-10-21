CREATE TABLE IF NOT EXISTS architecture_investigations (
    id uuid PRIMARY KEY,
    owner_id uuid NOT NULL REFERENCES website_accounts(id) ON DELETE CASCADE,
    title text NOT NULL,
    repository_name text NOT NULL,
    status text NOT NULL CHECK (status IN ('completed', 'incomplete')),
    schema_version integer NOT NULL CHECK (schema_version = 1),
    graph jsonb NOT NULL CHECK (jsonb_typeof(graph) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS architecture_investigations_owner_created
ON architecture_investigations(owner_id, created_at DESC);
