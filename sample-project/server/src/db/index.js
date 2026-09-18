'use strict';

const { Pool } = require('pg');

const config = require('../config');

/**
 * The Postgres connection pool, created on first use rather than at import time.
 *
 * Lazy creation matters for two reasons: `pg` must not open sockets in tests
 * that run against the in-memory repositories, and a module that throws at
 * import time is far harder to report on than one that fails on the call that
 * actually needed the database.
 */

/** @type {import('pg').Pool | null} */
let pool = null;

function getPool() {
  if (pool) return pool;

  pool = new Pool({
    connectionString: config.databaseUrl,
    max: 10,
    idleTimeoutMillis: 30_000,
    connectionTimeoutMillis: 5_000,
  });

  // Without a listener, a dropped backend connection crashes the process.
  pool.on('error', (error) => {
    console.error('[db] idle client error:', error.message);
  });

  return pool;
}

/**
 * Run a parameterised query.
 * @param {string} text SQL with $1, $2 placeholders
 * @param {unknown[]} [params]
 */
function query(text, params = []) {
  return getPool().query(text, params);
}

/**
 * Is the database reachable? Used by /health, so it swallows errors and
 * reports them as a flag instead of throwing.
 * @returns {Promise<boolean>}
 */
async function ping() {
  if (config.dbDriver === 'memory') return true;
  try {
    await query('SELECT 1');
    return true;
  } catch {
    return false;
  }
}

/** Close the pool. Called on shutdown; safe to call when no pool exists. */
async function close() {
  if (!pool) return;
  await pool.end();
  pool = null;
}

module.exports = { getPool, query, ping, close };
