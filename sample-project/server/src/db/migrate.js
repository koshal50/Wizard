'use strict';

/**
 * Migration runner.
 *
 *   npm run migrate --workspace server
 *
 * Applies every .sql file in src/db in filename order, recording each one in
 * `schema_migrations` so repeat runs are no-ops. Each file runs inside a
 * transaction: a failure leaves the database exactly as it was found.
 *
 * Note that the runner deliberately ignores DB_DRIVER — there is nothing to
 * migrate in the in-memory adapter, and silently doing nothing would be worse
 * than saying so.
 */

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const config = require('../config');
const db = require('./index');

const DB_DIR = __dirname;

/** Files to apply, in order. Add new migrations to the end of this list. */
const MIGRATIONS = ['schema.sql'];

function checksum(contents) {
  return crypto.createHash('sha256').update(contents).digest('hex');
}

async function ensureMigrationsTable() {
  await db.query(`
    CREATE TABLE IF NOT EXISTS schema_migrations (
      name       text PRIMARY KEY,
      checksum   text        NOT NULL,
      applied_at timestamptz NOT NULL DEFAULT now()
    )
  `);
}

async function appliedMigrations() {
  const { rows } = await db.query('SELECT name, checksum FROM schema_migrations');
  return new Map(rows.map((row) => [row.name, row.checksum]));
}

async function applyMigration(name, sql, digest) {
  const client = await db.getPool().connect();
  try {
    await client.query('BEGIN');
    await client.query(sql);
    await client.query(
      'INSERT INTO schema_migrations (name, checksum) VALUES ($1, $2)',
      [name, digest]
    );
    await client.query('COMMIT');
  } catch (error) {
    await client.query('ROLLBACK');
    throw error;
  } finally {
    client.release();
  }
}

async function migrate() {
  if (config.dbDriver === 'memory') {
    console.log('[migrate] DB_DRIVER=memory — nothing to migrate.');
    return { applied: [], skipped: MIGRATIONS };
  }

  console.log(`[migrate] target: ${describeTarget(config.databaseUrl)}`);
  await ensureMigrationsTable();
  const applied = await appliedMigrations();

  const result = { applied: [], skipped: [] };

  for (const name of MIGRATIONS) {
    const filePath = path.join(DB_DIR, name);
    if (!fs.existsSync(filePath)) {
      throw new Error(`Migration file not found: ${filePath}`);
    }

    const sql = fs.readFileSync(filePath, 'utf8');
    const digest = checksum(sql);
    const previous = applied.get(name);

    if (previous === digest) {
      result.skipped.push(name);
      console.log(`[migrate] skip   ${name} (already applied)`);
      continue;
    }

    if (previous && previous !== digest) {
      throw new Error(
        `${name} has changed since it was applied. Migrations must be immutable — ` +
          'add a new file instead of editing this one, or reset the database.'
      );
    }

    await applyMigration(name, sql, digest);
    result.applied.push(name);
    console.log(`[migrate] apply  ${name}`);
  }

  console.log(
    `[migrate] done: ${result.applied.length} applied, ${result.skipped.length} skipped.`
  );
  return result;
}

/** Strip the password from a connection string before logging it. */
function describeTarget(connectionString) {
  try {
    const url = new URL(connectionString);
    if (url.password) url.password = '***';
    return url.toString();
  } catch {
    return '(unparseable DATABASE_URL)';
  }
}

if (require.main === module) {
  migrate()
    .then(() => db.close())
    .then(() => process.exit(0))
    .catch(async (error) => {
      console.error(`[migrate] failed: ${error.message}`);
      await db.close().catch(() => {});
      process.exit(1);
    });
}

module.exports = { migrate, MIGRATIONS };
