# Taskboard

A small task and notes board with real authentication. Every user gets a private board of
tasks, each with a title, an optional description, a status, a priority and an optional due
date. Nothing is shared between accounts — a task that belongs to somebody else is
indistinguishable from a task that does not exist.

The repository is an npm workspace with two packages:

| Package  | Path      | What it is                                                   |
| -------- | --------- | ------------------------------------------------------------ |
| `server` | `server/` | Express + PostgreSQL JSON API, JWT auth, zod validation       |
| `client` | `client/` | React + Vite single page app that talks to the API over HTTP  |

## Features

- Email + password registration and login, bcrypt hashing, JWT access tokens with an expiry.
- Refresh tokens stored server side, so `POST /api/auth/logout` actually revokes a session
  instead of merely asking the browser to forget a string.
- Owner-scoped task CRUD, filterable by status and searchable by title.
- Request validation on every write path, with errors returned in a single predictable shape.
- Rate limiting on the credential endpoints, `helmet` security headers, CORS allow-list.
- A `/health` endpoint reporting process uptime and database reachability.

## Prerequisites

- **Node.js 18 or newer** (CI runs 20). The server uses `fetch` in health probes and the
  client's Vite 5 toolchain requires ESM.
- **PostgreSQL 13 or newer** — the schema relies on the built-in `gen_random_uuid()`.
  Any Postgres will do: a local install, the `docker-compose.yml` in this repo, or a hosted
  instance. If you would rather not run one at all, see *Running without Postgres* below.
- **npm 9 or newer** for npm workspaces.

## Getting started

Install everything once from the repository root — npm workspaces will install both packages:

```bash
npm install
```

A `package-lock.json` covering both workspaces is committed, so `npm ci` also works and
installs exactly the locked tree (that is what CI uses).

### 1. Configure the environment

```bash
cp .env.example .env
```

Open `.env` and set `JWT_SECRET` to a long random string. Every other value has a working
default. A secret can be generated with:

```bash
node -e "console.log(require('crypto').randomBytes(48).toString('hex'))"
```

The server refuses to boot if `JWT_SECRET` is missing or shorter than 32 characters.

### 2. Create the database schema

```bash
npm run migrate          # from the repository root
# or: npm run migrate --workspace server
```

The migration runner reads `server/src/db/schema.sql` and applies it idempotently, so running
it twice is safe. It records each applied file in a `schema_migrations` table.

### 3. Run the backend

```bash
npm run dev:server
```

The API listens on `http://localhost:4000` and reloads on change via nodemon. Verify it:

```bash
curl http://localhost:4000/health
```

### 4. Run the frontend

In a second terminal:

```bash
npm run dev:client
```

Vite serves the app on `http://localhost:5173` and proxies nothing — the browser calls the
API directly using `VITE_API_URL`, so the server's `CORS_ORIGIN` must match the Vite origin.

Both halves at once (installs `concurrently` at the root):

```bash
npm run dev
```

## Running without Postgres

The data access layer is a set of repositories with two interchangeable adapters: one on
`pg`, and one in-memory adapter used by the test suite. Set `DB_DRIVER=memory` to run the
whole API against process memory — handy for a quick smoke test, and it is what
`npm test` uses so the tests never need a database.

```bash
DB_DRIVER=memory npm run dev:server
```

Data set this way disappears when the process exits. Never use it outside local tinkering.

## Testing

```bash
npm test                        # both workspaces
npm run test --workspace server # jest + supertest
npm run test --workspace client # vitest + testing-library
```

The server suite boots the real Express app through supertest with `DB_DRIVER=memory`, so it
exercises routing, middleware, validation, services and the repositories together without a
database. `npm run test --workspace server -- --coverage` prints coverage.

Linting:

```bash
npm run lint
npm run lint --workspace server -- --fix
```

## Environment variables

All variables live in a single `.env` at the repository root; the server loads it with
`dotenv` and the client reads its one variable at build time.

| Variable                 | Default                                            | Used by | Notes                                                     |
| ------------------------ | -------------------------------------------------- | ------- | --------------------------------------------------------- |
| `NODE_ENV`               | `development`                                      | server  | `development`, `test` or `production`                      |
| `PORT`                   | `4000`                                             | server  | HTTP listen port                                           |
| `DATABASE_URL`           | `postgres://board:board@localhost:5432/board`      | server  | Postgres connection string                                 |
| `DB_DRIVER`              | `pg`                                               | server  | `pg` or `memory`                                           |
| `JWT_SECRET`             | — (required)                                       | server  | At least 32 characters; the server exits without it        |
| `JWT_EXPIRES_IN`         | `15m`                                              | server  | Access token lifetime, any `jsonwebtoken` duration string  |
| `REFRESH_TOKEN_TTL_DAYS` | `30`                                               | server  | How long a refresh token row stays valid                   |
| `BCRYPT_ROUNDS`          | `12`                                               | server  | Cost factor for password hashing                           |
| `CORS_ORIGIN`            | `http://localhost:5173`                            | server  | Comma-separated list of allowed browser origins            |
| `LOG_FORMAT`             | `dev`                                              | server  | `morgan` format; set to `combined` in production           |
| `RATE_LIMIT_WINDOW_MS`   | `900000`                                           | server  | Length of the login/register rate-limit window             |
| `RATE_LIMIT_MAX`         | `10`                                               | server  | Attempts allowed per window per IP                         |
| `VITE_API_URL`           | `http://localhost:4000/api`                        | client  | API root the browser calls; Vite inlines it at build time  |

## API

The full request/response reference lives in [`server/README.md`](server/README.md). Summary:

| Method   | Path                    | Auth | Purpose                          |
| -------- | ----------------------- | ---- | -------------------------------- |
| `GET`    | `/health`               | no   | Uptime and database connectivity |
| `POST`   | `/api/auth/register`    | no   | Create an account                |
| `POST`   | `/api/auth/login`       | no   | Exchange credentials for tokens  |
| `POST`   | `/api/auth/refresh`     | no   | Rotate an expired access token   |
| `POST`   | `/api/auth/logout`      | yes  | Revoke a refresh token           |
| `GET`    | `/api/auth/me`          | yes  | The authenticated user           |
| `GET`    | `/api/tasks`            | yes  | List the caller's tasks          |
| `POST`   | `/api/tasks`            | yes  | Create a task                    |
| `GET`    | `/api/tasks/:id`        | yes  | Read one task                    |
| `PATCH`  | `/api/tasks/:id`        | yes  | Update a task                    |
| `DELETE` | `/api/tasks/:id`        | yes  | Delete a task                    |

Successful responses are wrapped as `{ "data": ... }`; failures as
`{ "error": { "code", "message", "details?" } }`.

## Docker

`docker-compose.yml` starts Postgres, the API and the Vite dev server, with healthchecks so
the API waits for the database before migrating and starting.

```bash
docker compose up --build
docker compose down -v      # also drops the database volume
```

The compose file mounts the source tree and installs dependencies inside the containers, so
it works without a local Node install. It is a development convenience, not a deployment
recipe.

## Project layout

```
.
├── server/                 Express API
│   ├── src/
│   │   ├── app.js          builds the app (exported for tests)
│   │   ├── server.js       starts the listener, handles shutdown
│   │   ├── config/         env loading + zod validation, fails fast
│   │   ├── db/             pool, schema.sql, migration runner
│   │   ├── repositories/   pg and in-memory adapters behind one interface
│   │   ├── routes/         auth and task endpoints
│   │   ├── middleware/     auth guard, error handler, logger, rate limiter
│   │   ├── services/       business logic, no Express types
│   │   └── utils/          AppError, password hashing, token helpers
│   └── __tests__/          jest + supertest suites
├── client/                 React SPA
│   └── src/
│       ├── api/            axios instance and typed endpoint helpers
│       ├── context/        AuthContext + useAuth
│       ├── components/     ProtectedRoute, Navbar, TaskCard, TaskForm, Spinner, ErrorMessage
│       ├── pages/          Login, Register, Dashboard, NotFound
│       └── styles/         design tokens and component CSS
└── .github/workflows/ci.yml
```

## License

MIT
