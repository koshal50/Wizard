'use strict';

const crypto = require('crypto');
const jwt = require('jsonwebtoken');

const config = require('../config');
const AppError = require('./AppError');

/**
 * Access tokens are stateless JWTs: short lived and verified without a database
 * round trip.
 *
 * Refresh tokens are the opposite — random opaque strings whose SHA-256 lives in
 * a table, so a session can be revoked. A fast hash is enough here (unlike for
 * passwords) because the token is 48 random bytes; there is nothing to guess.
 */

/**
 * Sign a short-lived access token for a user.
 *
 * @param {{ id: string, email: string }} user
 * @returns {{ token: string, expiresAt: string }} JWT plus its ISO expiry, which
 *   the client stores so it can refresh before a request fails.
 */
function issueAccessToken(user) {
  const token = jwt.sign(
    { sub: user.id, email: user.email },
    config.jwtSecret,
    { expiresIn: config.jwtExpiresIn, issuer: 'taskboard' }
  );
  const { exp } = jwt.decode(token);
  return { token, expiresAt: new Date(exp * 1000).toISOString() };
}

/**
 * Verify an access token.
 *
 * Distinguishes expiry from corruption so the client can tell "log in again"
 * apart from "this token is junk", which callers map to different codes.
 *
 * @param {string} token
 * @returns {{ sub: string, email: string, iat: number, exp: number }}
 * @throws {AppError} 401 with code `TOKEN_EXPIRED` or `INVALID_TOKEN`
 */
function verifyAccessToken(token) {
  try {
    return jwt.verify(token, config.jwtSecret, { issuer: 'taskboard' });
  } catch (error) {
    if (error instanceof jwt.TokenExpiredError) {
      throw AppError.unauthorized('Access token has expired.', 'TOKEN_EXPIRED');
    }
    throw AppError.unauthorized('Access token is malformed or not valid.', 'INVALID_TOKEN');
  }
}

/**
 * Create a refresh token and the values needed to store it.
 * Only `token` is ever returned to the client; the database holds `tokenHash`.
 *
 * @returns {{ token: string, tokenHash: string, expiresAt: Date }}
 */
function generateRefreshToken() {
  const token = crypto.randomBytes(48).toString('hex');
  return {
    token,
    tokenHash: hashRefreshToken(token),
    expiresAt: refreshTokenExpiry(),
  };
}

/**
 * @param {string} token
 * @returns {string} hex SHA-256 of the token
 */
function hashRefreshToken(token) {
  return crypto.createHash('sha256').update(token).digest('hex');
}

/** @returns {Date} now + REFRESH_TOKEN_TTL_DAYS */
function refreshTokenExpiry() {
  const expiresAt = new Date();
  expiresAt.setDate(expiresAt.getDate() + config.refreshTokenTtlDays);
  return expiresAt;
}

module.exports = {
  issueAccessToken,
  verifyAccessToken,
  generateRefreshToken,
  hashRefreshToken,
  refreshTokenExpiry,
};
