'use strict';

const { getRepositories } = require('../repositories');
const AppError = require('../utils/AppError');

/**
 * Task board operations.
 *
 * Every function here takes the owner's id as its first argument, and every
 * query it makes is scoped by that id. Ownership is not checked afterwards —
 * there is no "fetch, then compare" step to forget.
 */

/** Allowed values, shared with the request schemas so they cannot drift. */
const TASK_STATUSES = ['todo', 'in_progress', 'done'];
const TASK_PRIORITIES = ['low', 'medium', 'high'];

/**
 * @param {string} userId
 * @param {{ status?: string, search?: string, sort?: string, order?: 'asc'|'desc' }} [filters]
 */
function listTasks(userId, filters = {}) {
  return getRepositories().tasks.listByUser(userId, filters);
}

/**
 * @param {string} userId
 * @param {object} input
 */
function createTask(userId, input) {
  return getRepositories().tasks.create(userId, input);
}

/**
 * Load one task.
 *
 * A row belonging to another user is reported as 404, not 403: a 403 would
 * confirm the id exists and turn the endpoint into a way to probe for other
 * people's task ids.
 *
 * @param {string} userId
 * @param {string} taskId
 * @throws {AppError} 404 when no such task exists for this owner
 */
async function getTask(userId, taskId) {
  const task = await getRepositories().tasks.findByIdForUser(taskId, userId);
  if (!task) {
    throw AppError.notFound('Task not found.', 'TASK_NOT_FOUND');
  }
  return task;
}

/**
 * Apply a partial update. Absent fields are left alone; fields explicitly set to
 * null are cleared, which is how the client removes a due date.
 *
 * @param {string} userId
 * @param {string} taskId
 * @param {object} patch
 */
async function updateTask(userId, taskId, patch) {
  const updated = await getRepositories().tasks.update(taskId, userId, patch);
  if (!updated) {
    throw AppError.notFound('Task not found.', 'TASK_NOT_FOUND');
  }
  return updated;
}

/**
 * @param {string} userId
 * @param {string} taskId
 * @throws {AppError} 404 when there was nothing to delete
 */
async function deleteTask(userId, taskId) {
  const removed = await getRepositories().tasks.remove(taskId, userId);
  if (!removed) {
    throw AppError.notFound('Task not found.', 'TASK_NOT_FOUND');
  }
}

module.exports = {
  TASK_STATUSES,
  TASK_PRIORITIES,
  listTasks,
  createTask,
  getTask,
  updateTask,
  deleteTask,
};
