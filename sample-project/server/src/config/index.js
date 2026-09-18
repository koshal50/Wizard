'use strict';

const fs = require('fs');
const path = require('path');

const dotenv = require('dotenv');
const { z } = require('zod');

/**
 * Environment loading and validation.
 *
 * Every value the process needs is parsed once, here, at require time. If
 * anything is missing or malformed the process prints what is wrong and exits,
 * rather than failing later at the first request that happens to need it.
 */

const rootEnvPath = path.resolve(__dirname, '..', '..', '..', '.env');
const serverEnvPath = path.resolve(__dirname, '..', '..', '.env');

// A .env next to the server package wins over the one at the repository root;
// neither overwrites variables that are already set in the real environment,
// which is what lets CI and the test setup inject values directly.
if (fs.existsSync(serverEnvPath)) dotenv.config({ path: serverEnvPath });
if (fs.existsSync(rootEnvPath)) dotenv.config({ path: rootEnvPath });

const schema = z.object({
  NODE_ENV: z.enum(['development', 'test', 'production']).default('development'),
  PORT: z.coerce.number().int().positive().max(65535).default(4000),

  DATABASE_URL: z
    .string()
    .min(1, 'DATABASE_URL must not be empty.')
    .default('postgres://board:board@localhost:5432/board'),
  DB_DRIVER: z.enum(['pg', 'memory']).default('pg'),

  JWT_SECRET: z
    .string()
    .min(32, 'JWT_SECRET must be at least 32 characters long.'),
  JWT_EXPIRES_IN: z
    .string()
    .regex(/^\d+\s*(s|m|h|d|w)?$/, 'JWT_EXPIRES_IN must look like "15m", "1h" or "7d".')
    .default('15m'),
  REFRESH_TOKEN_TTL_DAYS: z.coerce.number().int().positive().max(365).default(30),
  BCRYPT_ROUNDS: z.coerce.number().int().min(4).max(15).default(12),

  CORS_ORIGIN: z.string().default('http://localhost:5173'),
  LOG_FORMAT: z.string().default('dev'),
  RATE_LIMIT_WINDOW_MS: z.coerce.number().int().positive().default(15 * 60 * 1000),
  RATE_LIMIT_MAX: z.coerce.number().int().positive().default(10),
});

// Tests must run without a real secret in the environment, but production and
// development still get the fail-fast behaviour.
function withTestDefaults(env) {
  if (env.NODE_ENV !== 'test' || env.JWT_SECRET) return env;
  return { ...env, JWT_SECRET: 'test-only-secret-value-that-is-long-enough' };
}

const parsed = schema.safeParse(withTestDefaults(process.env));

if (!parsed.success) {
  const problems = parsed.error.issues
    .map((issue) => `  - ${issue.path.join('.') || '(root)'}: ${issue.message}`)
    .join('\n');

  console.error(`Invalid environment configuration:\n${problems}\n`);
  console.error('Copy .env.example to .env and fill in the missing values.');
  process.exit(1);
}

const env = parsed.data;

/** Comma-separated CORS_ORIGIN turned into the array `cors` expects. */
const corsOrigins = env.CORS_ORIGIN.split(',')
  .map((origin) => origin.trim())
  .filter(Boolean);

const config = Object.freeze({
  env: env.NODE_ENV,
  isProduction: env.NODE_ENV === 'production',
  isTest: env.NODE_ENV === 'test',

  port: env.PORT,
  databaseUrl: env.DATABASE_URL,
  dbDriver: env.DB_DRIVER,

  jwtSecret: env.JWT_SECRET,
  jwtExpiresIn: env.JWT_EXPIRES_IN,
  refreshTokenTtlDays: env.REFRESH_TOKEN_TTL_DAYS,
  bcryptRounds: env.BCRYPT_ROUNDS,

  corsOrigins,
  logFormat: env.LOG_FORMAT,
  rateLimit: {
    windowMs: env.RATE_LIMIT_WINDOW_MS,
    max: env.RATE_LIMIT_MAX,
  },
});

module.exports = config;
