'use strict';

const { getRepositories } = require('../repositories');
const AppError = require('../utils/AppError');
const { verifyAccessToken } = require('../utils/tokens');

/**
 * Authentication guard.
 *
 * Rejects a request unless it carries a valid, unexpired access token for a user
 * that still exists. The three failure modes are kept distinct in the response
 * code — `TOKEN_MISSING`, `TOKEN_EXPIRED`, `INVALID_TOKEN` — because the client
 * reacts differently to each: refresh, redirect, or give up.
 */

const BEARER_PATTERN = /^Bearer\s+(.+)$/i;

/**
 * @param {import('express').Request} req
 * @returns {string | null} the raw token
 */
function extractToken(req) {
  const header = req.get('authorization');
  if (!header) return null;

  const match = BEARER_PATTERN.exec(header.trim());
  if (!match) return null;

  const token = match[1].trim();
  return token.length > 0 ? token : null;
}

async function requireAuth(req, _res, next) {
  try {
    const token = extractToken(req);
    if (!token) {
      throw AppError.unauthorized('Missing bearer token.', 'TOKEN_MISSING');
    }

    const payload = verifyAccessToken(token);

    // The token is valid, but the account may have been deleted since it was
    // issued — a stateless token cannot know that on its own.
    const user = await getRepositories().users.findById(payload.sub);
    if (!user) {
      throw AppError.unauthorized('The account for this token no longer exists.', 'INVALID_TOKEN');
    }

    req.user = { id: user.id, email: user.email, name: user.name };
    req.auth = { token, expiresAt: new Date(payload.exp * 1000).toISOString() };
    return next();
  } catch (error) {
    return next(error);
  }
}

module.exports = { requireAuth, extractToken };
