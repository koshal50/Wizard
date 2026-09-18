'use strict';

const db = require('../db');
const AppError = require('../utils/AppError');

/**
 * PostgreSQL implementations of the repository interfaces.
 *
 * Two rules hold throughout this file:
 *   1. Never build SQL by concatenating values — everything user-supplied is a
 *      `$n` parameter. The one thing interpolated is a column name, and it comes
 *      from a fixed whitelist map, never from the request.
 *   2. Rows are mapped to a stable camelCase shape before they leave. `pg`
 *      returns Date objects for timestamptz and strings for date; the rest of the
 *      codebase should not have to care which driver it is talking to.
 */

/** Whitelist for ORDER BY. Keys are what the API accepts, values are columns. */
const SORT_COLUMNS = {
  createdAt: 'created_at',
  updatedAt: 'updated_at',
  dueDate: 'due_date',
  title: 'title',
};

/** Postgres error codes we translate instead of leaking to the client. */
const PG_UNIQUE_VIOLATION = '23505';
const PG_INVALID_TEXT_REPRESENTATION = '22P02';

function toUser(row) {
  if (!row) return null;
  return {
    id: row.id,
    email: row.email,
    name: row.name,
    passwordHash: row.password_hash,
    createdAt: toIso(row.created_at),
    updatedAt: toIso(row.updated_at),
  };
}

function toTask(row) {
  if (!row) return null;
  return {
    id: row.id,
    userId: row.user_id,
    title: row.title,
    description: row.description,
    status: row.status,
    priority: row.priority,
    // A `date` column arrives as 'YYYY-MM-DD' already; keep it as-is so the
    // client is not shifted by a timezone on the way through.
    dueDate: row.due_date instanceof Date ? row.due_date.toISOString().slice(0, 10) : row.due_date,
    createdAt: toIso(row.created_at),
    updatedAt: toIso(row.updated_at),
  };
}

function toToken(row) {
  if (!row) return null;
  return {
    id: row.id,
    userId: row.user_id,
    tokenHash: row.token_hash,
    expiresAt: toIso(row.expires_at),
    revokedAt: toIso(row.revoked_at),
    createdAt: toIso(row.created_at),
  };
}

function toIso(value) {
  if (!value) return null;
  return value instanceof Date ? value.toISOString() : value;
}

function createPgRepositories() {
  const users = {
    async create({ email, passwordHash, name }) {
      try {
        const { rows } = await db.query(
          `INSERT INTO users (email, password_hash, name)
           VALUES ($1, $2, $3)
           RETURNING *`,
          [email, passwordHash, name]
        );
        return toUser(rows[0]);
      } catch (error) {
        // Checked here rather than by a SELECT-then-INSERT in the service: two
        // simultaneous registrations would both pass that check, and only the
        // unique index can actually settle the race.
        if (error.code === PG_UNIQUE_VIOLATION) {
          throw AppError.conflict('An account with that email already exists.', 'EMAIL_TAKEN');
        }
        throw error;
      }
    },

    async findByEmail(email) {
      const { rows } = await db.query('SELECT * FROM users WHERE email = $1', [email]);
      return toUser(rows[0]);
    },

    async findById(id) {
      const { rows } = await db.query('SELECT * FROM users WHERE id = $1', [id]);
      return toUser(rows[0]);
    },
  };

  async function findByIdForUser(id, userId) {
    return runOrNull(() =>
      db
        .query('SELECT * FROM tasks WHERE id = $1 AND user_id = $2', [id, userId])
        .then(({ rows }) => toTask(rows[0]))
    );
  }

  const tasks = {
    async listByUser(userId, { status, search, sort = 'createdAt', order = 'desc' } = {}) {
      const params = [userId];
      const conditions = ['user_id = $1'];

      if (status) {
        params.push(status);
        conditions.push(`status = $${params.length}`);
      }

      if (search) {
        params.push(`%${search}%`);
        conditions.push(`(title ILIKE $${params.length} OR description ILIKE $${params.length})`);
      }

      const column = SORT_COLUMNS[sort] || SORT_COLUMNS.createdAt;
      const direction = order === 'asc' ? 'ASC' : 'DESC';
      // Undated tasks sink to the bottom when sorting by due date.
      const nulls = column === 'due_date' ? ' NULLS LAST' : '';

      const { rows } = await db.query(
        `SELECT * FROM tasks
          WHERE ${conditions.join(' AND ')}
          ORDER BY ${column} ${direction}${nulls}
          LIMIT 200`,
        params
      );
      return rows.map(toTask);
    },

    async create(userId, data) {
      const { rows } = await db.query(
        `INSERT INTO tasks (user_id, title, description, status, priority, due_date)
         VALUES ($1, $2, $3, $4, $5, $6)
         RETURNING *`,
        [
          userId,
          data.title,
          data.description ?? null,
          data.status ?? 'todo',
          data.priority ?? 'medium',
          data.dueDate ?? null,
        ]
      );
      return toTask(rows[0]);
    },

    findByIdForUser,

    async update(id, userId, patch) {
      const columns = {
        title: 'title',
        description: 'description',
        status: 'status',
        priority: 'priority',
        dueDate: 'due_date',
      };

      const params = [id, userId];
      const assignments = [];

      for (const [field, column] of Object.entries(columns)) {
        if (patch[field] !== undefined) {
          params.push(patch[field]);
          assignments.push(`${column} = $${params.length}`);
        }
      }

      // Nothing to change — return the row untouched rather than issuing an
      // UPDATE that would needlessly bump updated_at.
      if (assignments.length === 0) {
        return findByIdForUser(id, userId);
      }

      assignments.push('updated_at = now()');

      return runOrNull(() =>
        db
          .query(
            `UPDATE tasks
                SET ${assignments.join(', ')}
              WHERE id = $1 AND user_id = $2
              RETURNING *`,
            params
          )
          .then(({ rows }) => toTask(rows[0]))
      );
    },

    async remove(id, userId) {
      return runOrNull(async () => {
        const { rowCount } = await db.query('DELETE FROM tasks WHERE id = $1 AND user_id = $2', [
          id,
          userId,
        ]);
        return rowCount > 0;
      });
    },
  };

  const tokens = {
    async create({ userId, tokenHash, expiresAt }) {
      const { rows } = await db.query(
        `INSERT INTO refresh_tokens (user_id, token_hash, expires_at)
         VALUES ($1, $2, $3)
         RETURNING *`,
        [userId, tokenHash, expiresAt]
      );
      return toToken(rows[0]);
    },

    async findActiveByHash(tokenHash) {
      const { rows } = await db.query(
        `SELECT * FROM refresh_tokens
          WHERE token_hash = $1 AND revoked_at IS NULL AND expires_at > now()`,
        [tokenHash]
      );
      return toToken(rows[0]);
    },

    async revokeById(id) {
      const { rowCount } = await db.query(
        'UPDATE refresh_tokens SET revoked_at = now() WHERE id = $1 AND revoked_at IS NULL',
        [id]
      );
      return rowCount > 0;
    },

    async revokeAllForUser(userId) {
      const { rowCount } = await db.query(
        'UPDATE refresh_tokens SET revoked_at = now() WHERE user_id = $1 AND revoked_at IS NULL',
        [userId]
      );
      return rowCount;
    },

    async deleteStale() {
      const { rowCount } = await db.query(
        `DELETE FROM refresh_tokens
          WHERE expires_at < now()
             OR (revoked_at IS NOT NULL AND revoked_at < now() - interval '1 day')`
      );
      return rowCount;
    },
  };

  return { users, tasks, tokens };
}

/**
 * Postgres rejects a malformed uuid with 22P02 before it can match any row. A
 * request for `/api/tasks/not-a-uuid` means "no such task" as far as the caller
 * is concerned, so swallow that one code and let the caller answer 404.
 */
async function runOrNull(operation) {
  try {
    return await operation();
  } catch (error) {
    if (error.code === PG_INVALID_TEXT_REPRESENTATION) return null;
    throw error;
  }
}

module.exports = { createPgRepositories };
