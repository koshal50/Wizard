'use strict';

const { ZodError } = require('zod');

const config = require('../config');
const AppError = require('../utils/AppError');

/**
 * Error handling.
 *
 * Two middlewares, mounted last in app.js: `notFound` turns an unmatched route
 * into an AppError so every failure leaves through the same door, and
 * `errorHandler` turns whatever comes out of that door into the one response
 * shape the client knows how to read — `{ error: { code, message, details? } }`.
 *
 * Anything that is not an AppError or a ZodError is a bug: it is logged in full
 * and reported as a bare 500, because driver messages and stack traces are not
 * the client's business.
 */

function notFound(req, _res, next) {
  next(AppError.notFound(`Route ${req.method} ${req.originalUrl} does not exist.`, 'ROUTE_NOT_FOUND'));
}

/** Turn a ZodError into the 400 the client expects. */
function fromZodError(error) {
  const details = error.issues.map((issue) => ({
    field: issue.path.join('.') || '(body)',
    message: issue.message,
  }));
  const summary = details.map((detail) => `${detail.field}: ${detail.message}`).join('; ');
  return AppError.validation(`Request validation failed — ${summary}`, details);
}

/**
 * Express decides this is an error handler by its four-argument signature, so
 * `next` must stay in the list even though it is unused.
 */
// eslint-disable-next-line no-unused-vars
function errorHandler(error, req, res, _next) {
  let appError;

  if (error instanceof AppError) {
    appError = error;
  } else if (error instanceof ZodError) {
    appError = fromZodError(error);
  } else if (error.type === 'entity.parse.failed') {
    appError = new AppError(400, 'MALFORMED_JSON', 'Request body is not valid JSON.');
  } else if (error.type === 'entity.too.large') {
    appError = new AppError(413, 'PAYLOAD_TOO_LARGE', 'Request body is too large.');
  } else {
    appError = AppError.internal('An unexpected error occurred.', error);
  }

  const context = `${req.method} ${req.originalUrl}`;

  if (appError.statusCode >= 500) {
    console.error(`[error] ${context}`, error);
  } else if (!config.isTest) {
    console.warn(`[warn] ${context} -> ${appError.statusCode} ${appError.code}`);
  }

  const body = appError.toJSON();

  // In production a 500 says nothing beyond "it broke"; the detail is in the log.
  if (config.isProduction && appError.statusCode >= 500) {
    body.message = 'An unexpected error occurred.';
  }

  if (res.headersSent) return;
  res.status(appError.statusCode).json({ error: body });
}

module.exports = { notFound, errorHandler };
