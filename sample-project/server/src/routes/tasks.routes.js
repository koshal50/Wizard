'use strict';

const express = require('express');
const { z } = require('zod');

const { requireAuth } = require('../middleware/auth');
const taskService = require('../services/task.service');
const asyncHandler = require('../utils/asyncHandler');

const router = express.Router();

/**
 * Task routes.
 *
 * `requireAuth` is applied to the whole router, so there is no way to add an
 * endpoint here and forget the guard. Ownership is then enforced inside the
 * service, which scopes every query by `req.user.id`.
 */
router.use(requireAuth);

const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/;

/** Reject things like 2024-02-31, which the regex alone would let through. */
function isCalendarDate(value) {
  const parsed = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value;
}

const title = z
  .string({ required_error: 'Title is required.' })
  .trim()
  .min(1, 'Title is required.')
  .max(200, 'Title must be at most 200 characters.');

const description = z
  .string()
  .trim()
  .max(2000, 'Description must be at most 2000 characters.')
  .nullable();

const status = z.enum(taskService.TASK_STATUSES, {
  errorMap: () => ({ message: `Status must be one of: ${taskService.TASK_STATUSES.join(', ')}.` }),
});

const priority = z.enum(taskService.TASK_PRIORITIES, {
  errorMap: () => ({ message: `Priority must be one of: ${taskService.TASK_PRIORITIES.join(', ')}.` }),
});

const dueDate = z
  .string()
  .regex(DATE_ONLY, 'Due date must be in YYYY-MM-DD format.')
  .refine(isCalendarDate, 'Due date is not a real calendar date.')
  .nullable();

const createTaskSchema = z
  .object({
    title,
    description: description.optional(),
    status: status.optional(),
    priority: priority.optional(),
    dueDate: dueDate.optional(),
  })
  .strict();

// Everything optional, but null is only accepted where clearing the value makes
// sense. A null title is a client bug, not an instruction to blank the row.
const updateTaskSchema = z
  .object({
    title: title.optional(),
    description: description.optional(),
    status: status.optional(),
    priority: priority.optional(),
    dueDate: dueDate.optional(),
  })
  .strict()
  .refine((body) => Object.keys(body).length > 0, {
    message: 'Provide at least one field to update.',
  });

const listQuerySchema = z
  .object({
    status: status.optional(),
    search: z.string().trim().min(1).max(100).optional(),
    sort: z.enum(['createdAt', 'updatedAt', 'dueDate', 'title']).optional(),
    order: z.enum(['asc', 'desc']).optional(),
  })
  .strict();

const idParamSchema = z.object({
  id: z.string().uuid('Task id must be a UUID.'),
});

router.get(
  '/',
  asyncHandler(async (req, res) => {
    const filters = listQuerySchema.parse(req.query);
    const tasks = await taskService.listTasks(req.user.id, filters);
    res.json({ data: { tasks, count: tasks.length } });
  })
);

router.post(
  '/',
  asyncHandler(async (req, res) => {
    const input = createTaskSchema.parse(req.body);
    const task = await taskService.createTask(req.user.id, input);
    res.status(201).json({ data: { task } });
  })
);

router.get(
  '/:id',
  asyncHandler(async (req, res) => {
    const { id } = idParamSchema.parse(req.params);
    const task = await taskService.getTask(req.user.id, id);
    res.json({ data: { task } });
  })
);

router.patch(
  '/:id',
  asyncHandler(async (req, res) => {
    const { id } = idParamSchema.parse(req.params);
    const patch = updateTaskSchema.parse(req.body);
    const task = await taskService.updateTask(req.user.id, id, patch);
    res.json({ data: { task } });
  })
);

router.delete(
  '/:id',
  asyncHandler(async (req, res) => {
    const { id } = idParamSchema.parse(req.params);
    await taskService.deleteTask(req.user.id, id);
    res.status(204).send();
  })
);

module.exports = router;
