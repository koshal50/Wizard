'use strict';

const config = require('../config');
const { createMemoryRepositories } = require('./memory.repository');
const { createPgRepositories } = require('./pg.repository');

/**
 * Repository selection.
 *
 * Services never learn which adapter they are talking to: they ask for the
 * repository set and call methods on it. The instance is built lazily so that
 * requiring this module does not open a database connection, which keeps the
 * in-memory path free of `pg` side effects and lets the test suite reset state
 * between cases.
 */

let instance = null;

/** @returns {{ users: object, tasks: object, tokens: object }} */
function getRepositories() {
  if (!instance) {
    instance =
      config.dbDriver === 'memory' ? createMemoryRepositories() : createPgRepositories();
  }
  return instance;
}

/**
 * Empty the in-memory store. A no-op on the Postgres adapter, which owns its
 * own data — tests that need a clean database should truncate it explicitly.
 */
function resetRepositories() {
  if (instance && typeof instance.reset === 'function') {
    instance.reset();
  }
}

module.exports = { getRepositories, resetRepositories };
