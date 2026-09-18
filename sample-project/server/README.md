# Taskboard API

Express + PostgreSQL JSON API for the task board, with JWT authentication and
owner-scoped tasks. Part of the `taskboard` workspace — see the
[repository README](../README.md) for prerequisites and initial setup.

```bash
npm run dev          # nodemon, reloads on change
npm start            # plain node
npm run migrate      # apply src/db/schema.sql
npm test             # jest + supertest
npm run lint
```

## Response shape

Every successful response is wrapped in `data`:

```json
{ "data": { "task": { "id": "...", "title": "..." } } }
```

Every failure uses the same envelope, with a stable machine-readable `code`:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed — title: Title is required.",
    "details": [{ "field": "title", "message": "Title is required." }]
  }
}
```

| Status | Codes                                                                   |
| ------ | ----------------------------------------------------------------------- |
| 400    | `VALIDATION_ERROR`, `MALFORMED_JSON`                                     |
| 401    | `TOKEN_MISSING`, `TOKEN_EXPIRED`, `INVALID_TOKEN`, `INVALID_CREDENTIALS`, `INVALID_REFRESH_TOKEN` |
| 403    | `CORS_NOT_ALLOWED`                                                       |
| 404    | `TASK_NOT_FOUND`, `ROUTE_NOT_FOUND`                                      |
| 409    | `EMAIL_TAKEN`                                                           |
| 413    | `PAYLOAD_TOO_LARGE`                                                      |
| 429    | `RATE_LIMITED`                                                          |
| 500    | `INTERNAL_ERROR`                                                        |

## Endpoints

Authenticated routes expect `Authorization: Bearer <accessToken>`.

| Method   | Path                 | Auth | Body / query                                                     | Success |
| -------- | -------------------- | ---- | ---------------------------------------------------------------- | ------- |
| `GET`    | `/health`            | no   | —                                                                | `200` process uptime, version and `db.connected`; `503` when the database is unreachable |
| `POST`   | `/api/auth/register` | no   | `{ email, password (min 8), name }`                              | `201` session |
| `POST`   | `/api/auth/login`    | no   | `{ email, password }`                                            | `200` session |
| `POST`   | `/api/auth/refresh`  | no   | `{ refreshToken }`                                               | `200` session (the old refresh token is revoked) |
| `POST`   | `/api/auth/logout`   | yes  | `{ refreshToken? }` — omit to end every session                  | `200` `{ revoked: n }` |
| `GET`    | `/api/auth/me`       | yes  | —                                                                | `200` `{ user }` |
| `GET`    | `/api/tasks`         | yes  | `?status=&search=&sort=&order=`                                   | `200` `{ tasks, count }` |
| `POST`   | `/api/tasks`         | yes  | `{ title, description?, status?, priority?, dueDate? }`           | `201` `{ task }` |
| `GET`    | `/api/tasks/:id`     | yes  | —                                                                | `200` `{ task }` |
| `PATCH`  | `/api/tasks/:id`     | yes  | any subset of the create fields                                  | `200` `{ task }` |
| `DELETE` | `/api/tasks/:id`     | yes  | —                                                                | `204` no body |

### The session object

`register`, `login` and `refresh` all return the same shape:

```json
{
  "user": { "id": "uuid", "email": "ada@example.com", "name": "Ada", "createdAt": "...", "updatedAt": "..." },
  "accessToken": "eyJ...",
  "accessTokenExpiresAt": "2024-05-01T10:15:00.000Z",
  "refreshToken": "8f3c...",
  "refreshTokenExpiresAt": "2024-05-31T10:00:00.000Z"
}
```

The access token is a short-lived JWT (default 15 minutes) and is verified
without a database lookup. The refresh token is an opaque 96-character string;
only its SHA-256 is stored, and it is rotated on every use, so presenting one
twice fails the second time. Revoking a session means writing `revoked_at` on
that row, which is what `logout` does.

## Task fields

| Field         | Type                                | Notes                                          |
| ------------- | ----------------------------------- | ---------------------------------------------- |
| `id`          | uuid                                | server generated                               |
| `title`       | string, 1–200 characters            | required                                       |
| `description` | string up to 2000 characters, null  | send `null` to clear it                        |
| `status`      | `todo` \| `in_progress` \| `done`   | defaults to `todo`                             |
| `priority`    | `low` \| `medium` \| `high`         | defaults to `medium`                           |
| `dueDate`     | `YYYY-MM-DD`, null                  | send `null` to clear it                        |
| `createdAt`   | ISO 8601                            | server managed                                 |
| `updatedAt`   | ISO 8601                            | bumped on every write                          |

Query parameters for the list endpoint:

- `status` — exact match.
- `search` — case-insensitive substring of the title or the description.
- `sort` — `createdAt` (default), `updatedAt`, `dueDate` or `title`.
- `order` — `asc` or `desc` (default). Undated tasks sort last.

Unknown query parameters and unknown body fields are rejected with a 400 rather
than ignored, so a typo in a client fails loudly instead of silently doing
nothing.

## Ownership

Every task query is scoped by the authenticated user's id. Reading, updating or
deleting a task that belongs to somebody else returns **404**, not 403 — a 403
would confirm the id exists.

## Layers

```
request → route (zod validation) → service (rules) → repository (SQL)
                ↑                                        ↓
        middleware/auth                          pg | memory adapter
```

- `src/routes/` validates and serialises. No business rules.
- `src/services/` holds the rules and knows nothing about HTTP.
- `src/repositories/` owns persistence. Two interchangeable adapters implement
  one interface: `pg.repository.js` for Postgres, `memory.repository.js` for the
  test suite and for `DB_DRIVER=memory`.
- `src/middleware/` is transport concerns: the auth guard, logging, rate
  limiting and the error handler.

## Tests

```bash
npm test
npm run test:coverage
```

The suite runs on the in-memory adapter, so it needs no database. It boots the
real app through supertest, which means routing, validation, services, the error
handler and the response shape are all exercised — only the SQL itself is not.
`npm run migrate` against a real database in CI covers the schema.

Bcrypt rounds are lowered to 4 under `NODE_ENV=test`; hashing at the production
cost of 12 would add tens of seconds to the run.

## Environment

See [`../.env.example`](../.env.example). Configuration is validated by zod in
`src/config/index.js` at boot — a missing or malformed value exits the process
with an explanation instead of failing at the first request that needs it.
