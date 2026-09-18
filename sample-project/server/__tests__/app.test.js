'use strict';

const express = require('express');

const db = require('../src/db');
const config = require('../src/config');
const rateLimit = require('../src/middleware/rateLimiter');
const { errorHandler } = require('../src/middleware/errorHandler');
const { createTestApp, resetState, bearer, registerUser, request } = require('./setup');

/**
 * Cross-cutting behaviour: the health probe, the two terminal middlewares
 * (404 and error handling), CORS and rate limiting. None of it belongs to a
 * single resource, which is why it lives in its own file.
 */

let app;

beforeEach(() => {
  resetState();
  app = createTestApp();
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe('GET /health', () => {
  it('reports uptime and database connectivity', async () => {
    const response = await request(app).get('/health');

    expect(response.status).toBe(200);
    expect(response.body).toMatchObject({
      status: 'ok',
      version: expect.any(String),
      uptime: expect.any(Number),
      db: { connected: true, driver: config.dbDriver },
    });
    expect(response.body.uptime).toBeGreaterThanOrEqual(0);
    expect(Date.parse(response.body.timestamp)).not.toBeNaN();
  });

  it('answers 503 when the database is unreachable', async () => {
    jest.spyOn(db, 'ping').mockResolvedValue(false);

    const response = await request(app).get('/health');

    expect(response.status).toBe(503);
    expect(response.body).toMatchObject({ status: 'degraded', db: { connected: false } });
  });

  it('does not require a token', async () => {
    const response = await request(app).get('/health').set(bearer('garbage'));

    expect(response.status).toBe(200);
  });
});

describe('unmatched routes', () => {
  it('answers 404 with a route-aware message', async () => {
    const response = await request(app).get('/api/does-not-exist');

    expect(response.status).toBe(404);
    expect(response.body.error.code).toBe('ROUTE_NOT_FOUND');
    expect(response.body.error.message).toContain('/api/does-not-exist');
  });

  it('does not fall through to the task router', async () => {
    const response = await request(app).get('/api/tasks/1/2/3');

    // 401, not 404: `requireAuth` is applied to the whole task router, which is
    // the point of applying it there rather than per-route — no endpoint can be
    // added without the guard. It also means an unauthenticated caller cannot
    // probe which task routes exist, since the answer is the same for all of
    // them. What matters here is that the request never reaches task handling.
    expect(response.status).toBe(401);
    expect(response.body.error.code).toBe('TOKEN_MISSING');
  });

  it('answers 404 under the task router once authenticated', async () => {
    const { accessToken } = await registerUser(app);

    const response = await request(app).get('/api/tasks/1/2/3').set(bearer(accessToken));

    // Past the guard, the router matches nothing, so the app's 404 is reached.
    expect(response.status).toBe(404);
    expect(response.body.error.code).toBe('ROUTE_NOT_FOUND');
  });
});

describe('malformed requests', () => {
  it('answers 400 for a body that is not JSON', async () => {
    const response = await request(app)
      .post('/api/auth/login')
      .set('Content-Type', 'application/json')
      .send('{"email": ');

    expect(response.status).toBe(400);
    expect(response.body.error.code).toBe('MALFORMED_JSON');
  });

  it('answers 413 for an oversized body', async () => {
    const response = await request(app)
      .post('/api/tasks')
      .set(bearer('irrelevant'))
      .send({ title: 'x'.repeat(200 * 1024) });

    expect(response.status).toBe(413);
    expect(response.body.error.code).toBe('PAYLOAD_TOO_LARGE');
  });
});

describe('CORS', () => {
  it('allows the configured origin', async () => {
    const response = await request(app).get('/health').set('Origin', config.corsOrigins[0]);

    expect(response.status).toBe(200);
    expect(response.headers['access-control-allow-origin']).toBe(config.corsOrigins[0]);
  });

  it('refuses any other origin', async () => {
    const response = await request(app).get('/health').set('Origin', 'https://evil.example');

    expect(response.status).toBe(403);
    expect(response.body.error.code).toBe('CORS_NOT_ALLOWED');
  });

  it('allows requests with no Origin header at all', async () => {
    const response = await request(app).get('/health');

    expect(response.status).toBe(200);
  });
});

describe('rate limiting', () => {
  /** A throwaway app so the limit can be set low without touching the real one. */
  function limitedApp(max) {
    const mini = express();
    mini.get(
      '/limited',
      rateLimit({ windowMs: 60_000, max, message: 'Too many attempts.' }),
      (_req, res) => res.json({ data: { ok: true } })
    );
    mini.use(errorHandler);
    return mini;
  }

  it('allows requests up to the limit', async () => {
    const mini = limitedApp(2);

    expect((await request(mini).get('/limited')).status).toBe(200);
    expect((await request(mini).get('/limited')).status).toBe(200);
  });

  it('answers 429 once the window is full, with a Retry-After header', async () => {
    const mini = limitedApp(1);

    await request(mini).get('/limited');
    const blocked = await request(mini).get('/limited');

    expect(blocked.status).toBe(429);
    expect(blocked.body.error.code).toBe('RATE_LIMITED');
    expect(Number(blocked.headers['retry-after'])).toBeGreaterThan(0);
    expect(blocked.headers['ratelimit-remaining']).toBe('0');
  });

  it('counts failures too, so password guessing is throttled', async () => {
    // One shared limiter across two routes, the way the auth router uses it.
    const mini = express();
    const limiter = rateLimit({ windowMs: 60_000, max: 3 });
    mini.post('/login', limiter, (_req, res) => res.status(401).json({ error: { code: 'NOPE' } }));
    mini.use(errorHandler);

    for (let attempt = 0; attempt < 3; attempt += 1) {
      const response = await request(mini).post('/login').send({});
      expect(response.status).toBe(401);
    }

    const blocked = await request(mini).post('/login').send({});
    expect(blocked.status).toBe(429);
  });
});
