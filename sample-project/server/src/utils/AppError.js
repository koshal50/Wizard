'use strict';

/**
 * An error that is safe to show to a client.
 *
 * Anything thrown that is *not* an AppError is treated as a bug by the error
 * handler, logged in full, and reported to the caller as a generic 500 — that
 * split is what keeps stack traces and driver messages out of responses.
 */
class AppError extends Error {
  /**
   * @param {number} statusCode HTTP status to send.
   * @param {string} code Stable machine-readable code, e.g. `EMAIL_TAKEN`.
   * @param {string} message Human-readable message.
   * @param {object} [options]
   * @param {unknown} [options.details] Extra context, serialised into the response.
   * @param {Error} [options.cause] Original error, kept for logs only.
   */
  constructor(statusCode, code, message, { details, cause } = {}) {
    super(message);
    this.name = 'AppError';
    this.statusCode = statusCode;
    this.code = code;
    this.details = details;
    this.isOperational = true;
    if (cause) this.cause = cause;
    Error.captureStackTrace(this, AppError);
  }

  static validation(message, details) {
    return new AppError(400, 'VALIDATION_ERROR', message, { details });
  }

  static unauthorized(message = 'Authentication required.', code = 'UNAUTHORIZED') {
    return new AppError(401, code, message);
  }

  /** Used for another user's rows too: a 403 there would confirm the row exists. */
  static notFound(message = 'Resource not found.', code = 'NOT_FOUND') {
    return new AppError(404, code, message);
  }

  static conflict(message, code = 'CONFLICT') {
    return new AppError(409, code, message);
  }

  static tooManyRequests(message = 'Too many requests. Please slow down.') {
    return new AppError(429, 'RATE_LIMITED', message);
  }

  static internal(message = 'Something went wrong.', cause) {
    const error = new AppError(500, 'INTERNAL_ERROR', message, { cause });
    error.isOperational = false;
    return error;
  }

  toJSON() {
    const body = { code: this.code, message: this.message };
    if (this.details !== undefined) body.details = this.details;
    return body;
  }
}

module.exports = AppError;
