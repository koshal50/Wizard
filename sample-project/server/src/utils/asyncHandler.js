'use strict';

/**
 * Wrap an async route handler so a rejected promise reaches the error
 * middleware.
 *
 * Express 4 only understands errors passed to `next()`; without this wrapper an
 * `await` that throws leaves the request hanging until it times out.
 *
 * @param {(req, res, next) => Promise<unknown>} handler
 * @returns {import('express').RequestHandler}
 */
function asyncHandler(handler) {
  return function wrapped(req, res, next) {
    Promise.resolve(handler(req, res, next)).catch(next);
  };
}

module.exports = asyncHandler;
