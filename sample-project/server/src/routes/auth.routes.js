'use strict';

const express = require('express');
const { z } = require('zod');

const config = require('../config');
const { requireAuth } = require('../middleware/auth');
const rateLimit = require('../middleware/rateLimiter');
const authService = require('../services/auth.service');
const asyncHandler = require('../utils/asyncHandler');

const router = express.Router();

/**
 * Auth routes.
 *
 * Bodies are parsed by zod before any service runs, so the services can assume
 * well-formed input. A ZodError thrown here is turned into a 400 with a
 * per-field breakdown by the error handler.
 */

const email = z
  .string({ required_error: 'Email is required.' })
  .trim()
  .min(1, 'Email is required.')
  .max(254, 'Email is too long.')
  .email('Enter a valid email address.');

const password = z
  .string({ required_error: 'Password is required.' })
  .min(8, 'Password must be at least 8 characters.')
  .max(128, 'Password must be at most 128 characters.');

const registerSchema = z
  .object({
    email,
    password,
    name: z
      .string({ required_error: 'Name is required.' })
      .trim()
      .min(1, 'Name is required.')
      .max(80, 'Name must be at most 80 characters.'),
  })
  .strict();

const loginSchema = z
  .object({
    email,
    // Not the full password policy: an existing account's password only has to
    // be non-empty to be compared, and rejecting a short one here would leak
    // the policy for accounts created before a rule changed.
    password: z.string({ required_error: 'Password is required.' }).min(1, 'Password is required.'),
  })
  .strict();

const refreshSchema = z
  .object({ refreshToken: z.string().min(1, 'Refresh token is required.') })
  .strict();

const logoutSchema = z
  .object({ refreshToken: z.string().min(1).optional() })
  .strict();

// Credential endpoints get their own limiter, well below the app-wide default:
// this is the one pair of routes worth brute-forcing.
const credentialsLimiter = rateLimit({
  windowMs: config.rateLimit.windowMs,
  max: config.rateLimit.max,
  message: 'Too many authentication attempts. Please try again later.',
});

router.post(
  '/register',
  credentialsLimiter,
  asyncHandler(async (req, res) => {
    const input = registerSchema.parse(req.body);
    const session = await authService.register(input);
    res.status(201).json({ data: session });
  })
);

router.post(
  '/login',
  credentialsLimiter,
  asyncHandler(async (req, res) => {
    const input = loginSchema.parse(req.body);
    const session = await authService.login(input);
    res.json({ data: session });
  })
);

router.post(
  '/refresh',
  credentialsLimiter,
  asyncHandler(async (req, res) => {
    const input = refreshSchema.parse(req.body);
    const session = await authService.refresh(input);
    res.json({ data: session });
  })
);

router.post(
  '/logout',
  requireAuth,
  asyncHandler(async (req, res) => {
    const { refreshToken } = logoutSchema.parse(req.body ?? {});
    const result = await authService.logout({ userId: req.user.id, refreshToken });
    res.json({ data: result });
  })
);

router.get(
  '/me',
  requireAuth,
  asyncHandler(async (req, res) => {
    const user = await authService.getCurrentUser(req.user.id);
    res.json({ data: { user } });
  })
);

module.exports = router;
