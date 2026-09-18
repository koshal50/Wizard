'use strict';

const morgan = require('morgan');

const config = require('../config');

/**
 * HTTP request logging.
 *
 * Off in tests so a failing assertion is not buried in a wall of request lines,
 * and switched to `combined` in production via LOG_FORMAT where the output is
 * meant for a log aggregator rather than a terminal.
 */
const requestLogger = morgan(config.logFormat, {
  skip: () => config.isTest,
  // Colourised `dev` output only makes sense on a TTY; morgan handles that
  // itself, this just keeps the health probe from dominating the log.
  stream: process.stdout,
});

module.exports = requestLogger;
