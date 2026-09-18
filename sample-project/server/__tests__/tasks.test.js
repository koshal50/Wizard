'use strict';

const { createTestApp, resetState, registerUser, bearer, request } = require('./setup');

/**
 * Task CRUD and ownership.
 *
 * The ownership cases are the point of this file: every operation is repeated
 * against a second account, and the expected answer is always 404 — never 403,
 * which would confirm that the id exists.
 */

let app;
let owner;
let intruder;

beforeEach(async () => {
  resetState();
  app = createTestApp();
  owner = await registerUser(app, { email: 'owner@example.com', name: 'Owner' });
  intruder = await registerUser(app, { email: 'intruder@example.com', name: 'Intruder' });
});

function createTask(as, body) {
  return request(app).post('/api/tasks').set(bearer(as.accessToken)).send(body);
}

describe('POST /api/tasks', () => {
  it('requires authentication', async () => {
    const response = await request(app).post('/api/tasks').send({ title: 'No token' });

    expect(response.status).toBe(401);
    expect(response.body.error.code).toBe('TOKEN_MISSING');
  });

  it('creates a task with sensible defaults', async () => {
    const response = await createTask(owner, { title: 'Write the migration' });

    expect(response.status).toBe(201);
    expect(response.body.data.task).toMatchObject({
      title: 'Write the migration',
      description: null,
      status: 'todo',
      priority: 'medium',
      dueDate: null,
    });
    expect(response.body.data.task.id).toEqual(expect.any(String));
    expect(response.body.data.task.createdAt).toEqual(expect.any(String));
  });

  it('accepts every documented field', async () => {
    const response = await createTask(owner, {
      title: 'Ship it',
      description: 'Cut the release and tag it.',
      status: 'in_progress',
      priority: 'high',
      dueDate: '2030-01-31',
    });

    expect(response.status).toBe(201);
    expect(response.body.data.task).toMatchObject({
      status: 'in_progress',
      priority: 'high',
      dueDate: '2030-01-31',
    });
  });

  it.each([
    ['an empty title', { title: '   ' }],
    ['a title over the length limit', { title: 'x'.repeat(201) }],
    ['an unknown status', { title: 'Fine', status: 'archived' }],
    ['an unknown priority', { title: 'Fine', priority: 'urgent' }],
    ['a due date in the wrong format', { title: 'Fine', dueDate: '31/01/2030' }],
    ['a due date that is not a real day', { title: 'Fine', dueDate: '2030-02-31' }],
    ['an unexpected field', { title: 'Fine', assignee: 'someone@example.com' }],
    ['no title at all', { description: 'orphan' }],
  ])('rejects %s with 400', async (_label, body) => {
    const response = await createTask(owner, body);

    expect(response.status).toBe(400);
    expect(response.body.error.code).toBe('VALIDATION_ERROR');
  });
});

describe('GET /api/tasks', () => {
  it('returns only the caller\'s tasks', async () => {
    await createTask(owner, { title: 'Owner task' });
    await createTask(intruder, { title: 'Intruder task' });

    const response = await request(app).get('/api/tasks').set(bearer(owner.accessToken));

    expect(response.status).toBe(200);
    expect(response.body.data.count).toBe(1);
    expect(response.body.data.tasks.map((task) => task.title)).toEqual(['Owner task']);
  });

  it('returns an empty list for a new account', async () => {
    const response = await request(app).get('/api/tasks').set(bearer(owner.accessToken));

    expect(response.status).toBe(200);
    expect(response.body.data.tasks).toEqual([]);
  });

  it('filters by status', async () => {
    await createTask(owner, { title: 'Todo one' });
    await createTask(owner, { title: 'Done one', status: 'done' });

    const response = await request(app)
      .get('/api/tasks?status=done')
      .set(bearer(owner.accessToken));

    expect(response.body.data.tasks.map((task) => task.title)).toEqual(['Done one']);
  });

  it('searches the title and the description', async () => {
    await createTask(owner, { title: 'Renew the certificate' });
    await createTask(owner, { title: 'Unrelated', description: 'mentions certificate too' });
    await createTask(owner, { title: 'Nothing to do with it' });

    const response = await request(app)
      .get('/api/tasks?search=certificate')
      .set(bearer(owner.accessToken));

    expect(response.body.data.count).toBe(2);
  });

  it('rejects an unknown query parameter', async () => {
    const response = await request(app)
      .get('/api/tasks?ownerId=someone-else')
      .set(bearer(owner.accessToken));

    expect(response.status).toBe(400);
    expect(response.body.error.code).toBe('VALIDATION_ERROR');
  });

  it('sorts by title when asked', async () => {
    await createTask(owner, { title: 'Beta' });
    await createTask(owner, { title: 'Alpha' });

    const response = await request(app)
      .get('/api/tasks?sort=title&order=asc')
      .set(bearer(owner.accessToken));

    expect(response.body.data.tasks.map((task) => task.title)).toEqual(['Alpha', 'Beta']);
  });
});

describe('GET /api/tasks/:id', () => {
  it('returns the task to its owner', async () => {
    const created = await createTask(owner, { title: 'Mine' });

    const response = await request(app)
      .get(`/api/tasks/${created.body.data.task.id}`)
      .set(bearer(owner.accessToken));

    expect(response.status).toBe(200);
    expect(response.body.data.task.title).toBe('Mine');
  });

  it("returns 404 for another user's task, not 403", async () => {
    const created = await createTask(owner, { title: 'Mine' });

    const response = await request(app)
      .get(`/api/tasks/${created.body.data.task.id}`)
      .set(bearer(intruder.accessToken));

    expect(response.status).toBe(404);
    expect(response.body.error.code).toBe('TASK_NOT_FOUND');
  });

  it('returns 404 for an id that does not exist', async () => {
    const response = await request(app)
      .get('/api/tasks/6f1b1f2e-0000-4000-8000-000000000000')
      .set(bearer(owner.accessToken));

    expect(response.status).toBe(404);
  });

  it('returns 400 for an id that is not a uuid', async () => {
    const response = await request(app)
      .get('/api/tasks/not-a-uuid')
      .set(bearer(owner.accessToken));

    expect(response.status).toBe(400);
    expect(response.body.error.code).toBe('VALIDATION_ERROR');
  });
});

describe('PATCH /api/tasks/:id', () => {
  it('applies a partial update and leaves the other fields alone', async () => {
    const created = await createTask(owner, {
      title: 'Draft',
      description: 'Still rough',
      priority: 'low',
    });

    const response = await request(app)
      .patch(`/api/tasks/${created.body.data.task.id}`)
      .set(bearer(owner.accessToken))
      .send({ status: 'done' });

    expect(response.status).toBe(200);
    expect(response.body.data.task).toMatchObject({
      title: 'Draft',
      description: 'Still rough',
      priority: 'low',
      status: 'done',
    });
  });

  it('clears a nullable field when it is explicitly null', async () => {
    const created = await createTask(owner, { title: 'Has a date', dueDate: '2030-01-31' });

    const response = await request(app)
      .patch(`/api/tasks/${created.body.data.task.id}`)
      .set(bearer(owner.accessToken))
      .send({ dueDate: null });

    expect(response.status).toBe(200);
    expect(response.body.data.task.dueDate).toBeNull();
  });

  it('rejects a null title', async () => {
    const created = await createTask(owner, { title: 'Draft' });

    const response = await request(app)
      .patch(`/api/tasks/${created.body.data.task.id}`)
      .set(bearer(owner.accessToken))
      .send({ title: null });

    expect(response.status).toBe(400);
  });

  it('rejects an empty patch', async () => {
    const created = await createTask(owner, { title: 'Draft' });

    const response = await request(app)
      .patch(`/api/tasks/${created.body.data.task.id}`)
      .set(bearer(owner.accessToken))
      .send({});

    expect(response.status).toBe(400);
    expect(response.body.error.code).toBe('VALIDATION_ERROR');
  });

  it("cannot touch another user's task, and does not change it", async () => {
    const created = await createTask(owner, { title: 'Hands off' });
    const id = created.body.data.task.id;

    const response = await request(app)
      .patch(`/api/tasks/${id}`)
      .set(bearer(intruder.accessToken))
      .send({ title: 'Hijacked' });

    expect(response.status).toBe(404);

    const reread = await request(app).get(`/api/tasks/${id}`).set(bearer(owner.accessToken));
    expect(reread.body.data.task.title).toBe('Hands off');
  });
});

describe('DELETE /api/tasks/:id', () => {
  it('deletes the task and returns 204', async () => {
    const created = await createTask(owner, { title: 'Temporary' });
    const id = created.body.data.task.id;

    const response = await request(app)
      .delete(`/api/tasks/${id}`)
      .set(bearer(owner.accessToken));

    expect(response.status).toBe(204);
    expect(response.body).toEqual({});

    const reread = await request(app).get(`/api/tasks/${id}`).set(bearer(owner.accessToken));
    expect(reread.status).toBe(404);
  });

  it("cannot delete another user's task", async () => {
    const created = await createTask(owner, { title: 'Survivor' });
    const id = created.body.data.task.id;

    const response = await request(app)
      .delete(`/api/tasks/${id}`)
      .set(bearer(intruder.accessToken));

    expect(response.status).toBe(404);

    const reread = await request(app).get(`/api/tasks/${id}`).set(bearer(owner.accessToken));
    expect(reread.status).toBe(200);
  });
});
