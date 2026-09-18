'use strict';

const AppError = require('../utils/AppError');

/**
 * Fixed-window rate limiter, keyed by client IP and route.
 *
 * Written by hand rather than pulled in as a dependency because the rules here
 * are simple and the state is per-process. It counts requests, not successes, so
 * a burst of wrong passwords is throttled just as hard as a burst of right ones.
 *
 * Caveat worth knowing: state lives in the process, so behind more than one
 * instance each replica enforces its own limit. Move the counter to Redis before
 * relying on this for anything more than slowing down a script.
 *
 * @param {object} options
 * @param {number} options.windowMs window length in milliseconds
 * @param {number} options.max requests allowed per window per key
 * @param {string} [options.message] error message for the 429
 * @returns {import('express').RequestHandler}
 */
function rateLimit({ windowMs, max, message = 'Too many requests. Please try again later.' }) {
  /** @type {Map<string, { count: number, resetAt: number }>} */
  const hits = new Map();

  // Sweep expired windows so a long-running process does not grow this map
  // without bound. `unref` keeps this timer from holding the process open.
  const sweeper = setInterval(() => {
    const now = Date.now();
    for (const [key, entry] of hits) {
      if (entry.resetAt <= now) hits.delete(key);
    }
  }, windowMs);
  if (typeof sweeper.unref === 'function') sweeper.unref();

  const middleware = (req, res, next) => {
    const key = `${req.ip}:${req.baseUrl}${req.path}`;
    const now = Date.now();
    const entry = hits.get(key);

    if (!entry || entry.resetAt <= now) {
      hits.set(key, { count: 1, resetAt: now + windowMs });
    } else {
      entry.count += 1;
    }

    const current = hits.get(key);
    const remaining = Math.max(0, max - current.count);
    const retryAfterSeconds = Math.ceil((current.resetAt - now) / 1000);

    // Standard RateLimit headers: clients and proxies can back off without
    // parsing our error body.
    res.set('RateLimit-Limit', String(max));
    res.set('RateLimit-Remaining', String(remaining));
    res.set('RateLimit-Reset', String(retryAfterSeconds));

    if (current.count > max) {
      res.set('Retry-After', String(retryAfterSeconds));
      return next(AppError.tooManyRequests(message));
    }

    return next();
  };

  return middleware;
}

module.exports = rateLimit;
