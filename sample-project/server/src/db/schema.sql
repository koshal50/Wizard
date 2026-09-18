-- Taskboard schema.
--
-- Applied by src/db/migrate.js. Statements are written to be safe to run twice,
-- so a half-finished migration can simply be re-run.
--
-- Requires PostgreSQL 13+ for the built-in gen_random_uuid().

CREATE TABLE IF NOT EXISTS users (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  -- Stored lowercased by the auth service; the unique constraint is what
  -- turns a duplicate registration into a 409 instead of a second account.
  email         text        NOT NULL UNIQUE,
  password_hash text        NOT NULL,
  name          text        NOT NULL,
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tasks (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     uuid        NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  title       text        NOT NULL,
  description text,
  status      text        NOT NULL DEFAULT 'todo'
                CHECK (status IN ('todo', 'in_progress', 'done')),
  priority    text        NOT NULL DEFAULT 'medium'
                CHECK (priority IN ('low', 'medium', 'high')),
  due_date    date,
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);

-- The board is always read owner-first, newest-first.
CREATE INDEX IF NOT EXISTS tasks_user_created_idx ON tasks (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS tasks_user_status_idx ON tasks (user_id, status);

CREATE TABLE IF NOT EXISTS refresh_tokens (
  id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    uuid        NOT NULL REFERENCES users (id) ON DELETE CASCADE,
  -- SHA-256 of the token handed to the client. The token itself is never stored,
  -- so a database dump alone cannot be replayed as a session.
  token_hash text        NOT NULL UNIQUE,
  expires_at timestamptz NOT NULL,
  -- Set on logout. Kept as a separate column from deletion so an audit of
  -- revoked sessions stays possible.
  revoked_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS refresh_tokens_user_idx ON refresh_tokens (user_id);
