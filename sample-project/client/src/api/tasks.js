import api from './client.js';

/**
 * Task endpoints.
 *
 * Thin wrappers over the API that unwrap the `{ data }` envelope, so components
 * deal in tasks and not in response bodies. Errors reject with the normalised
 * Error the interceptors produce — callers only need `error.message`.
 */

/**
 * @param {{ status?: string, search?: string, sort?: string, order?: string }} [filters]
 * @returns {Promise<{ tasks: object[], count: number }>}
 */
export async function listTasks(filters = {}) {
  // Empty values are dropped rather than sent: the API rejects unknown or empty
  // query parameters instead of ignoring them.
  const params = Object.fromEntries(
    Object.entries(filters).filter(([, value]) => value !== '' && value != null)
  );

  const response = await api.get('/tasks', { params });
  return response.data.data;
}

export async function createTask(input) {
  const response = await api.post('/tasks', input);
  return response.data.data.task;
}

export async function updateTask(id, patch) {
  const response = await api.patch(`/tasks/${id}`, patch);
  return response.data.data.task;
}

/** Resolves with no value: the API answers 204. */
export async function deleteTask(id) {
  await api.delete(`/tasks/${id}`);
}
