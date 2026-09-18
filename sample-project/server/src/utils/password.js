'use strict';

const bcrypt = require('bcryptjs');

const config = require('../config');

/**
 * bcryptjs ships a callback API; promisify the two calls we need so callers can
 * stay in async/await land.
 */

/**
 * Hash a plaintext password with the configured cost factor.
 * @param {string} plain
 * @returns {Promise<string>} `$2a$<rounds>$<salt><digest>`
 */
function hashPassword(plain) {
  return bcrypt.hash(plain, config.bcryptRounds);
}

/**
 * Compare a plaintext password against a stored hash.
 *
 * Always resolves to a boolean: a malformed hash in the database is a data
 * problem, not something the caller should have to catch.
 *
 * @param {string} plain
 * @param {string} hash
 * @returns {Promise<boolean>}
 */
async function verifyPassword(plain, hash) {
  try {
    return await bcrypt.compare(plain, hash);
  } catch {
    return false;
  }
}

module.exports = { hashPassword, verifyPassword };
