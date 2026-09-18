'use strict';

const jwt = require('jsonwebtoken');

const config = require('../src/config');
const { createTestApp, resetState, registerUser, bearer, request, DEFAULT_PASSWORD } = require('./setup');

/**
 * Registration, login, the guard, and session revocation.
 *
 * The suite drives the real Express app through supertest, so a passing test
 * means the whole stack worked: zod schemas, service rules, repository calls and
 * the error handler's response shape.
 */

let app;

beforeEach(() => {
  resetState();
  app = createTestApp();
});

describe('POST /api/auth/register', () => {
  it('creates an account and returns a session', async () => {
    const response = await request(app).post('/api/auth/register').send({
      email: 'ada@example.com',
      password: DEFAULT_PASSWORD,
      name: 'Ada Lovelace',
    });

    expect(response.status).toBe(201);
    expect(response.body.data.user).toMatchObject({
      email: 'ada@example.com',
      name: 'Ada Lovelace',
    });
    expect(response.body.data.user.id).toEqual(expect.any(String));
    expect(response.body.data.accessToken).toEqual(expect.any(String));
    expect(response.body.data.refreshToken).toEqual(expect.any(String));
  });

  it('never puts the password or its hash in the response', async () => {
    const response = await request(app).post('/api/auth/register').send({
      email: 'ada@example.com',
      password: DEFAULT_PASSWORD,
      name: 'Ada Lovelace',
    });

    const serialised = JSON.stringify(response.body);
    expect(serialised).not.toContain(DEFAULT_PASSWORD);
    expect(serialised).not.toContain('passwordHash');
    expect(response.body.data.user).not.toHaveProperty('password');
  });

  it('rejects a duplicate email with 409', async () => {
    await registerUser(app, { email: 'taken@example.com' });

    const response = await request(app).post('/api/auth/register').send({
      email: 'taken@example.com',
      password: DEFAULT_PASSWORD,
      name: 'Someone Else',
    });

    expect(response.status).toBe(409);
    expect(response.body.error.code).toBe('EMAIL_TAKEN');
  });

  it('treats emails as case-insensitive', async () => {
    await registerUser(app, { email: 'ada@example.com' });

    const response = await request(app).post('/api/auth/register').send({
      email: 'ADA@Example.COM',
      password: DEFAULT_PASSWORD,
      name: 'Ada Again',
    });

    expect(response.status).toBe(409);
    expect(response.body.error.code).toBe('EMAIL_TAKEN');
  });

  it('rejects a password under the minimum length', async () => {
    const response = await request(app).post('/api/auth/register').send({
      email: 'ada@example.com',
      password: 'short',
      name: 'Ada Lovelace',
    });

    expect(response.status).toBe(400);
    expect(response.body.error.code).toBe('VALIDATION_ERROR');
    expect(response.body.error.details).toEqual(
      expect.arrayContaining([expect.objectContaining({ field: 'password' })])
    );
  });

  it('rejects an unknown field rather than ignoring it', async () => {
    const response = await request(app).post('/api/auth/register').send({
      email: 'ada@example.com',
      password: DEFAULT_PASSWORD,
      name: 'Ada Lovelace',
      role: 'admin',
    });

    expect(response.status).toBe(400);
    expect(response.body.error.code).toBe('VALIDATION_ERROR');
  });
});

describe('POST /api/auth/login', () => {
  it('returns a session for correct credentials', async () => {
    const { credentials } = await registerUser(app, { email: 'ada@example.com' });

    const response = await request(app).post('/api/auth/login').send(credentials);

    expect(response.status).toBe(200);
    expect(response.body.data.user.email).toBe('ada@example.com');
    expect(response.body.data.accessToken).toEqual(expect.any(String));
    expect(response.body.data.refreshToken).toEqual(expect.any(String));
  });

  it('rejects a wrong password with 401', async () => {
    await registerUser(app, { email: 'ada@example.com' });

    const response = await request(app)
      .post('/api/auth/login')
      .send({ email: 'ada@example.com', password: 'not-the-password' });

    expect(response.status).toBe(401);
    expect(response.body.error.code).toBe('INVALID_CREDENTIALS');
  });

  it('answers an unknown email exactly like a wrong password', async () => {
    const unknown = await request(app)
      .post('/api/auth/login')
      .send({ email: 'nobody@example.com', password: 'not-the-password' });

    await registerUser(app, { email: 'ada@example.com' });
    const wrongPassword = await request(app)
      .post('/api/auth/login')
      .send({ email: 'ada@example.com', password: 'not-the-password' });

    // Identical status and message: nothing here tells an attacker which
    // addresses have accounts.
    expect(unknown.status).toBe(401);
    expect(unknown.body.error.code).toBe('INVALID_CREDENTIALS');
    expect(unknown.body).toEqual(wrongPassword.body);
  });
});

describe('GET /api/auth/me', () => {
  it('rejects a request with no token', async () => {
    const response = await request(app).get('/api/auth/me');

    expect(response.status).toBe(401);
    expect(response.body.error.code).toBe('TOKEN_MISSING');
  });

  it('rejects a malformed token', async () => {
    const response = await request(app).get('/api/auth/me').set(bearer('not.a.jwt'));

    expect(response.status).toBe(401);
    expect(response.body.error.code).toBe('INVALID_TOKEN');
  });

  it('rejects a token signed with a different secret', async () => {
    const forged = jwt.sign({ sub: 'someone', email: 'someone@example.com' }, 'a-different-secret-that-is-long-enough', {
      expiresIn: '15m',
      issuer: 'taskboard',
    });

    const response = await request(app).get('/api/auth/me').set(bearer(forged));

    expect(response.status).toBe(401);
    expect(response.body.error.code).toBe('INVALID_TOKEN');
  });

  it('rejects an expired token', async () => {
    const { user } = await registerUser(app);
    const expired = jwt.sign({ sub: user.id, email: user.email }, config.jwtSecret, {
      expiresIn: '-10s',
      issuer: 'taskboard',
    });

    const response = await request(app).get('/api/auth/me').set(bearer(expired));

    expect(response.status).toBe(401);
    expect(response.body.error.code).toBe('TOKEN_EXPIRED');
  });

  it('returns the current user for a valid token', async () => {
    const { accessToken, credentials } = await registerUser(app, { name: 'Ada Lovelace' });

    const response = await request(app).get('/api/auth/me').set(bearer(accessToken));

    expect(response.status).toBe(200);
    expect(response.body.data.user).toMatchObject({
      email: credentials.email,
      name: 'Ada Lovelace',
    });
  });
});

describe('POST /api/auth/logout', () => {
  it('requires authentication', async () => {
    const response = await request(app).post('/api/auth/logout').send({});

    expect(response.status).toBe(401);
  });

  it('revokes the refresh token it is given', async () => {
    const { accessToken, refreshToken } = await registerUser(app);

    const logout = await request(app)
      .post('/api/auth/logout')
      .set(bearer(accessToken))
      .send({ refreshToken });

    expect(logout.status).toBe(200);
    expect(logout.body.data.revoked).toBe(1);

    // The revoked token is worthless: this is the whole point of storing it.
    const reuse = await request(app).post('/api/auth/refresh').send({ refreshToken });
    expect(reuse.status).toBe(401);
    expect(reuse.body.error.code).toBe('INVALID_REFRESH_TOKEN');
  });

  it('revokes every session when no token is named', async () => {
    const first = await registerUser(app);
    const second = await request(app)
      .post('/api/auth/login')
      .send(first.credentials)
      .then((response) => response.body.data);

    const logout = await request(app).post('/api/auth/logout').set(bearer(second.accessToken)).send({});

    expect(logout.status).toBe(200);
    expect(logout.body.data.revoked).toBeGreaterThanOrEqual(2);

    for (const token of [first.refreshToken, second.refreshToken]) {
      const reuse = await request(app).post('/api/auth/refresh').send({ refreshToken: token });
      expect(reuse.status).toBe(401);
    }
  });
});

describe('POST /api/auth/refresh', () => {
  it('exchanges a refresh token for a new pair', async () => {
    const { refreshToken } = await registerUser(app);

    const response = await request(app).post('/api/auth/refresh').send({ refreshToken });

    expect(response.status).toBe(200);
    expect(response.body.data.accessToken).toEqual(expect.any(String));
    expect(response.body.data.refreshToken).not.toBe(refreshToken);
  });

  it('rotates: the old refresh token cannot be used twice', async () => {
    const { refreshToken } = await registerUser(app);

    await request(app).post('/api/auth/refresh').send({ refreshToken });
    const replay = await request(app).post('/api/auth/refresh').send({ refreshToken });

    expect(replay.status).toBe(401);
    expect(replay.body.error.code).toBe('INVALID_REFRESH_TOKEN');
  });

  it('rejects garbage', async () => {
    const response = await request(app)
      .post('/api/auth/refresh')
      .send({ refreshToken: 'a'.repeat(96) });

    expect(response.status).toBe(401);
    expect(response.body.error.code).toBe('INVALID_REFRESH_TOKEN');
  });
});
