'use strict';

const { getRepositories } = require('../repositories');
const AppError = require('../utils/AppError');
const { hashPassword, verifyPassword } = require('../utils/password');
const {
  issueAccessToken,
  generateRefreshToken,
  hashRefreshToken,
} = require('../utils/tokens');

/**
 * Authentication.
 *
 * Owns the account rules — what a session looks like, when a refresh token is
 * spent, how a duplicate email is reported — and nothing about HTTP. The routes
 * decide how these results are serialised.
 */

/**
 * A bcrypt hash of an arbitrary string, used only to burn the same amount of
 * CPU when the email does not exist as when the password is merely wrong.
 * Without it, response time alone reveals which addresses have accounts.
 */
const TIMING_DECOY_HASH = '$2a$10$N9qo8uLOickgx2ZMRZoMyeIjZAgcfl7p92ldGxad68LJZdL17lhWy';

/** The only user fields that ever leave the server. */
function toPublicUser(user) {
  return {
    id: user.id,
    email: user.email,
    name: user.name,
    createdAt: user.createdAt,
    updatedAt: user.updatedAt,
  };
}

/** Emails are case-insensitive in practice; normalise once, at the edge. */
function normaliseEmail(email) {
  return email.trim().toLowerCase();
}

/**
 * Mint an access/refresh pair and persist the refresh token.
 * @param {object} user
 */
async function createSession(user) {
  const access = issueAccessToken(user);
  const refresh = generateRefreshToken();

  await getRepositories().tokens.create({
    userId: user.id,
    tokenHash: refresh.tokenHash,
    expiresAt: refresh.expiresAt,
  });

  return {
    user: toPublicUser(user),
    accessToken: access.token,
    accessTokenExpiresAt: access.expiresAt,
    refreshToken: refresh.token,
    refreshTokenExpiresAt: refresh.expiresAt.toISOString(),
  };
}

/**
 * Create an account and log it straight in, so the client never has to make a
 * second round trip after registering.
 *
 * @param {{ email: string, password: string, name: string }} input
 */
async function register({ email, password, name }) {
  const repositories = getRepositories();
  const normalised = normaliseEmail(email);

  // Checked up front for a friendly error; the unique index is what actually
  // guarantees it under concurrency.
  const existing = await repositories.users.findByEmail(normalised);
  if (existing) {
    throw AppError.conflict('An account with that email already exists.', 'EMAIL_TAKEN');
  }

  const user = await repositories.users.create({
    email: normalised,
    passwordHash: await hashPassword(password),
    name: name.trim(),
  });

  return createSession(user);
}

/**
 * Verify credentials and start a session.
 *
 * A wrong password and an unknown email produce the same 401 with the same
 * message, so the endpoint cannot be used to discover who has an account.
 *
 * @param {{ email: string, password: string }} input
 */
async function login({ email, password }) {
  const repositories = getRepositories();
  const user = await repositories.users.findByEmail(normaliseEmail(email));

  if (!user) {
    await verifyPassword(password, TIMING_DECOY_HASH);
    throw AppError.unauthorized('Email or password is incorrect.', 'INVALID_CREDENTIALS');
  }

  if (!(await verifyPassword(password, user.passwordHash))) {
    throw AppError.unauthorized('Email or password is incorrect.', 'INVALID_CREDENTIALS');
  }

  return createSession(user);
}

/**
 * Trade a refresh token for a fresh pair, revoking the one presented.
 *
 * Rotation means a stolen refresh token is usable at most once, and the genuine
 * client's next attempt fails loudly instead of silently sharing a session.
 *
 * @param {{ refreshToken: string }} input
 */
async function refresh({ refreshToken }) {
  const repositories = getRepositories();
  const record = await repositories.tokens.findActiveByHash(hashRefreshToken(refreshToken));

  if (!record) {
    throw AppError.unauthorized(
      'Refresh token is invalid, expired or already revoked.',
      'INVALID_REFRESH_TOKEN'
    );
  }

  const user = await repositories.users.findById(record.userId);
  if (!user) {
    throw AppError.unauthorized('The account for this session no longer exists.', 'INVALID_TOKEN');
  }

  await repositories.tokens.revokeById(record.id);

  return createSession(user);
}

/**
 * Revoke the presented refresh token, or every session for the user when none is
 * given. Deliberately succeeds either way — a client asking to be logged out
 * should end up logged out even if its token was already spent.
 *
 * @param {{ userId: string, refreshToken?: string }} input
 * @returns {Promise<{ revoked: number }>}
 */
async function logout({ userId, refreshToken }) {
  const repositories = getRepositories();

  if (refreshToken) {
    const record = await repositories.tokens.findActiveByHash(hashRefreshToken(refreshToken));
    // Only revoke a token that belongs to the caller: a valid token for another
    // account must not be usable as a way to log that account out.
    if (record && record.userId === userId) {
      await repositories.tokens.revokeById(record.id);
      return { revoked: 1 };
    }
    const revoked = await repositories.tokens.revokeAllForUser(userId);
    return { revoked };
  }

  const revoked = await repositories.tokens.revokeAllForUser(userId);
  return { revoked };
}

/**
 * @param {string} userId
 * @returns {Promise<object>} the public user
 */
async function getCurrentUser(userId) {
  const user = await getRepositories().users.findById(userId);
  if (!user) {
    throw AppError.unauthorized('The account no longer exists.', 'INVALID_TOKEN');
  }
  return toPublicUser(user);
}

/**
 * Drop refresh tokens that have expired or were revoked over a day ago.
 *
 * Called once at boot from server.js rather than on a timer: at this scale the
 * table stays small, and a failed cleanup must never take the API down with it.
 *
 * @returns {Promise<number>} rows removed
 */
async function purgeStaleTokens() {
  try {
    return await getRepositories().tokens.deleteStale();
  } catch (error) {
    console.warn(`[auth] could not purge stale refresh tokens: ${error.message}`);
    return 0;
  }
}

module.exports = {
  register,
  login,
  refresh,
  logout,
  getCurrentUser,
  purgeStaleTokens,
};
