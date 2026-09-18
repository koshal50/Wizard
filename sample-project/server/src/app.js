'use strict';

const cors = require('cors');
const express = require('express');
const helmet = require('helmet');

const config = require('./config');
const db = require('./db');
const { errorHandler, notFound } = require('./middleware/errorHandler');
const requestLogger = require('./middleware/requestLogger');
const authRoutes = require('./routes/auth.routes');
const taskRoutes = require('./routes/tasks.routes');
const asyncHandler = require('./utils/asyncHandler');
const AppError = require('./utils/AppError');
const { version } = require('../package.json');

/**
 * Build the Express application.
 *
 * Exported as a factory rather than a ready-made instance so the test suite can
 * mount it directly with supertest — no port, no listener, no shutdown dance.
 * Starting the process is server.js's job.
 */
function createApp() {
  const app = express();

  app.disable('x-powered-by');

  // Behind a load balancer the socket address is the proxy's; without this every
  // request would share one rate-limit bucket.
  if (config.isProduction) app.set('trust proxy', 1);

  app.use(helmet());
  app.use(cors({ origin: corsOrigin, credentials: true }));
  app.use(express.json({ limit: '100kb' }));
  app.use(requestLogger);

  app.get(
    '/health',
    asyncHandler(async (_req, res) => {
      const connected = await db.ping();
      res.status(connected ? 200 : 503).json({
        status: connected ? 'ok' : 'degraded',
        version,
        uptime: Number(process.uptime().toFixed(3)),
        timestamp: new Date().toISOString(),
        db: { connected, driver: config.dbDriver },
      });
    })
  );

  app.use('/api/auth', authRoutes);
  app.use('/api/tasks', taskRoutes);

  // Last in, first out: nothing below this point can match a route.
  app.use(notFound);
  app.use(errorHandler);

  return app;
}

/**
 * Allow the configured origins, plus any request without an Origin header —
 * curl, health probes and server-to-server calls do not send one.
 */
function corsOrigin(origin, callback) {
  if (!origin) return callback(null, true);
  if (config.corsOrigins.includes('*') || config.corsOrigins.includes(origin)) {
    return callback(null, true);
  }
  return callback(
    new AppError(403, 'CORS_NOT_ALLOWED', `Origin ${origin} is not allowed to call this API.`)
  );
}

module.exports = { createApp };
