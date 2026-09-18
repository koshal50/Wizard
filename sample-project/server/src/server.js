'use strict';

const config = require('./config');
const db = require('./db');
const { createApp } = require('./app');
const authService = require('./services/auth.service');

/**
 * Process entry point: bind the port, then keep the process alive until told to
 * stop. Everything else about the API lives in app.js.
 */

const app = createApp();
const server = app.listen(config.port, () => {
  console.log(`[server] listening on http://localhost:${config.port} (${config.env})`);
  console.log(`[server] database driver: ${config.dbDriver}`);

  // Best-effort housekeeping; failures are logged, never fatal.
  authService.purgeStaleTokens().then((removed) => {
    if (removed > 0) console.log(`[server] purged ${removed} stale refresh token(s)`);
  });
});

server.on('error', (error) => {
  if (error.code === 'EADDRINUSE') {
    console.error(`[server] port ${config.port} is already in use. Set PORT to something else.`);
    process.exit(1);
  }
  throw error;
});

/**
 * Stop accepting connections, let in-flight requests finish, then close the
 * pool. A second signal skips the wait — otherwise a stuck request means the
 * only way out is `kill -9`.
 */
let shuttingDown = false;

function shutdown(signal) {
  if (shuttingDown) {
    console.warn(`[server] ${signal} received again, exiting immediately.`);
    process.exit(1);
  }
  shuttingDown = true;
  console.log(`[server] ${signal} received, shutting down.`);

  const forceExit = setTimeout(() => {
    console.warn('[server] shutdown timed out, exiting.');
    process.exit(1);
  }, 10_000);
  forceExit.unref();

  server.close(async () => {
    try {
      await db.close();
    } catch (error) {
      console.error(`[server] error closing the database pool: ${error.message}`);
    }
    console.log('[server] bye.');
    process.exit(0);
  });
}

process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));

process.on('unhandledRejection', (reason) => {
  console.error('[server] unhandled promise rejection:', reason);
});
