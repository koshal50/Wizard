'use strict';

const crypto = require('crypto');

const AppError = require('../utils/AppError');

/**
 * In-memory implementations of the repository interfaces.
 *
 * Used by the test suite (via DB_DRIVER=memory) and by anyone who wants to run
 * the API without a database. It is not a SQL engine — it implements exactly the
 * handful of operations the services ask for, which is why the queries the real
 * adapter needs stay in pg.repository.js where they belong.
 *
 * Both adapters are deliberately interchangeable, error behaviour included: a
 * duplicate email throws the same AppError here as it does on Postgres.
 */

const SORTABLE = {
  createdAt: 'createdAt',
  updatedAt: 'updatedAt',
  dueDate: 'dueDate',
  title: 'title',
};

function nowIso() {
  return new Date().toISOString();
}

function newId() {
  return crypto.randomUUID();
}

function createMemoryRepositories() {
  const state = {
    users: [],
    tasks: [],
    refreshTokens: [],
  };

  const users = {
    async create({ email, passwordHash, name }) {
      if (state.users.some((user) => user.email === email)) {
        throw AppError.conflict('An account with that email already exists.', 'EMAIL_TAKEN');
      }
      const timestamp = nowIso();
      const user = {
        id: newId(),
        email,
        passwordHash,
        name,
        createdAt: timestamp,
        updatedAt: timestamp,
      };
      state.users.push(user);
      return { ...user };
    },

    async findByEmail(email) {
      const user = state.users.find((candidate) => candidate.email === email);
      return user ? { ...user } : null;
    },

    async findById(id) {
      const user = state.users.find((candidate) => candidate.id === id);
      return user ? { ...user } : null;
    },
  };

  const tasks = {
    async listByUser(userId, { status, search, sort = 'createdAt', order = 'desc' } = {}) {
      const needle = search ? search.toLowerCase() : null;

      const rows = state.tasks.filter((task) => {
        if (task.userId !== userId) return false;
        if (status && task.status !== status) return false;
        if (needle) {
          const haystack = `${task.title} ${task.description || ''}`.toLowerCase();
          if (!haystack.includes(needle)) return false;
        }
        return true;
      });

      const key = SORTABLE[sort] || SORTABLE.createdAt;
      const direction = order === 'asc' ? 1 : -1;

      return rows
        .sort((a, b) => {
          const left = a[key] ?? '';
          const right = b[key] ?? '';
          if (left === right) return 0;
          return left > right ? direction : -direction;
        })
        .map((task) => ({ ...task }));
    },

    async create(userId, data) {
      const timestamp = nowIso();
      const task = {
        id: newId(),
        userId,
        title: data.title,
        description: data.description ?? null,
        status: data.status ?? 'todo',
        priority: data.priority ?? 'medium',
        dueDate: data.dueDate ?? null,
        createdAt: timestamp,
        updatedAt: timestamp,
      };
      state.tasks.push(task);
      return { ...task };
    },

    /**
     * Scoped by user on purpose: asking for somebody else's task returns null,
     * which the service turns into a 404 rather than a 403.
     */
    async findByIdForUser(id, userId) {
      const task = state.tasks.find((candidate) => candidate.id === id && candidate.userId === userId);
      return task ? { ...task } : null;
    },

    async update(id, userId, patch) {
      const task = state.tasks.find((candidate) => candidate.id === id && candidate.userId === userId);
      if (!task) return null;

      for (const [key, value] of Object.entries(patch)) {
        if (value !== undefined) task[key] = value;
      }
      task.updatedAt = nowIso();
      return { ...task };
    },

    async remove(id, userId) {
      const index = state.tasks.findIndex(
        (candidate) => candidate.id === id && candidate.userId === userId
      );
      if (index === -1) return false;
      state.tasks.splice(index, 1);
      return true;
    },
  };

  const tokens = {
    async create({ userId, tokenHash, expiresAt }) {
      const record = {
        id: newId(),
        userId,
        tokenHash,
        expiresAt: expiresAt instanceof Date ? expiresAt.toISOString() : expiresAt,
        revokedAt: null,
        createdAt: nowIso(),
      };
      state.refreshTokens.push(record);
      return { ...record };
    },

    async findActiveByHash(tokenHash) {
      const record = state.refreshTokens.find(
        (candidate) =>
          candidate.tokenHash === tokenHash &&
          candidate.revokedAt === null &&
          candidate.expiresAt > nowIso()
      );
      return record ? { ...record } : null;
    },

    async revokeById(id) {
      const record = state.refreshTokens.find((candidate) => candidate.id === id);
      if (!record || record.revokedAt) return false;
      record.revokedAt = nowIso();
      return true;
    },

    async revokeAllForUser(userId) {
      let count = 0;
      for (const record of state.refreshTokens) {
        if (record.userId === userId && record.revokedAt === null) {
          record.revokedAt = nowIso();
          count += 1;
        }
      }
      return count;
    },

    /** Housekeeping: drop rows that expired or were revoked more than a day ago. */
    async deleteStale() {
      const cutoff = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
      const before = state.refreshTokens.length;
      state.refreshTokens = state.refreshTokens.filter(
        (record) => record.expiresAt > nowIso() && !(record.revokedAt && record.revokedAt < cutoff)
      );
      return before - state.refreshTokens.length;
    },
  };

  return {
    users,
    tasks,
    tokens,
    /** Drop everything. Used between test cases. */
    reset() {
      state.users.length = 0;
      state.tasks.length = 0;
      state.refreshTokens.length = 0;
    },
    /** Direct access for assertions that need to poke at stored rows. */
    _state: state,
  };
}

module.exports = { createMemoryRepositories };
