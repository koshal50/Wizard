'use strict';

/**
 * Test bootstrap.
 *
 * Listed under `setupFiles` in package.json, so it runs before any test file and
 * before anything the test file requires — that ordering is what lets the
 * environment below take effect, since src/config validates the environment once
 * at require time.
 *
 * It also exports the small helpers the suites share; `require('./setup')` from
 * a test returns this same, already-initialised module.
 */

process.env.NODE_ENV = 'test';
// The in-memory adapter keeps the suite free of a database dependency.
process.env.DB_DRIVER = 'memory';
process.env.JWT_SECRET = 'test-secret-that-is-definitely-long-enough-to-pass';
process.env.JWT_EXPIRES_IN = '15m';
process.env.REFRESH_TOKEN_TTL_DAYS = '30';
// Deliberately below the production cost: bcrypt at 12 rounds would add tens of
// seconds across the suite, and nothing here is testing bcrypt itself.
process.env.BCRYPT_ROUNDS = '4';
process.env.CORS_ORIGIN = 'http://localhost:5173';
process.env.LOG_FORMAT = 'tiny';
// High enough that ordinary tests never trip the limiter; the limiter's own test
// builds a separate instance with a low limit.
process.env.RATE_LIMIT_MAX = '1000';
process.env.RATE_LIMIT_WINDOW_MS = '60000';

const request = require('supertest');

const { createApp } = require('../src/app');
const { resetRepositories } = require('../src/repositories');

const DEFAULT_PASSWORD = 'correct-horse-battery';

let userCounter = 0;

/**
 * A fresh Express app. Building one per test file is cheap and keeps a failure
 * from leaking middleware state into the next file.
 */
function createTestApp() {
  return createApp();
}

/** Empty the in-memory store. Call between tests. */
function resetState() {
  resetRepositories();
  userCounter = 0;
}

/**
 * Register a user through the real endpoint and return everything a test needs
 * to act as them.
 *
 * `credentials` is deliberately only `{ email, password }` — exactly a login
 * body. The auth schemas are `.strict()`, so an extra field is a 400, and a
 * caller that posts this object to /auth/login must not have to strip `name`
 * first.
 *
 * @param {import('express').Express} app
 * @param {{ email?: string, password?: string, name?: string }} [overrides]
 */
async function registerUser(app, overrides = {}) {
  userCounter += 1;
  const credentials = {
    email: overrides.email || `user${userCounter}@example.com`,
    password: overrides.password || DEFAULT_PASSWORD,
    name: overrides.name || `Test User ${userCounter}`,
  };

  const response = await request(app).post('/api/auth/register').send(credentials);

  if (response.status !== 201) {
    throw new Error(
      `registerUser failed: ${response.status} ${JSON.stringify(response.body)}`
    );
  }

  return {
    credentials: { email: credentials.email, password: credentials.password },
    user: response.body.data.user,
    accessToken: response.body.data.accessToken,
    refreshToken: response.body.data.refreshToken,
  };
}

/** `Authorization` header for a token. */
function bearer(token) {
  return { Authorization: `Bearer ${token}` };
}

module.exports = {
  createTestApp,
  resetState,
  registerUser,
  bearer,
  request,
  DEFAULT_PASSWORD,
};
