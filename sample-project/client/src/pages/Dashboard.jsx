import { useEffect, useMemo, useState } from 'react';

import { createTask, deleteTask, listTasks, updateTask } from '../api/tasks.js';
import ErrorMessage from '../components/ErrorMessage.jsx';
import Spinner from '../components/Spinner.jsx';
import TaskCard from '../components/TaskCard.jsx';
import TaskForm from '../components/TaskForm.jsx';
import { useAuth } from '../context/AuthContext.jsx';

/** Typing in the search box should not fire a request per keystroke. */
const SEARCH_DEBOUNCE_MS = 300;

function todayIso() {
  return new Date().toISOString().slice(0, 10);
}

export default function Dashboard() {
  const { user } = useAuth();

  const [tasks, setTasks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [actionError, setActionError] = useState(null);

  const [searchInput, setSearchInput] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [query, setQuery] = useState({ status: '', search: '' });
  const [reloadToken, setReloadToken] = useState(0);

  const [editingTask, setEditingTask] = useState(null);
  const [saving, setSaving] = useState(false);
  const [pendingDelete, setPendingDelete] = useState(null);
  const [deleting, setDeleting] = useState(false);

  // Collapse keystrokes into one filter change, and keep the same object when
  // nothing actually changed so the fetch effect below is not re-run.
  useEffect(() => {
    const timer = setTimeout(() => {
      const next = { status: statusFilter, search: searchInput.trim() };
      setQuery((previous) =>
        previous.status === next.status && previous.search === next.search ? previous : next
      );
    }, SEARCH_DEBOUNCE_MS);

    return () => clearTimeout(timer);
  }, [searchInput, statusFilter]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);

    listTasks(query)
      .then((data) => {
        if (cancelled) return;
        setTasks(data.tasks);
        setLoadError(null);
      })
      .catch((error) => {
        if (cancelled) return;
        setLoadError(error);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    // A response that arrives after the filters changed must not overwrite the
    // newer one.
    return () => {
      cancelled = true;
    };
  }, [query, reloadToken]);

  const stats = useMemo(() => {
    const today = todayIso();
    return {
      total: tasks.length,
      open: tasks.filter((task) => task.status !== 'done').length,
      done: tasks.filter((task) => task.status === 'done').length,
      overdue: tasks.filter(
        (task) => task.status !== 'done' && task.dueDate && task.dueDate < today
      ).length,
    };
  }, [tasks]);

  const filtersActive = Boolean(query.search || query.status);

  // With no filter active, the server's order is newest first, so prepending the
  // new task is exactly what a refetch would produce. With a filter active the
  // new task may not match it, and only the server can say — so refetch.
  function afterMutation(task, replaceId) {
    if (filtersActive) {
      setReloadToken((token) => token + 1);
      return;
    }
    setTasks((previous) =>
      replaceId
        ? previous.map((existing) => (existing.id === replaceId ? task : existing))
        : [task, ...previous]
    );
  }

  async function handleCreate(values) {
    setSaving(true);
    try {
      const task = await createTask(values);
      afterMutation(task);
      setActionError(null);
    } finally {
      setSaving(false);
    }
    // Errors are left to propagate: TaskForm renders them next to the fields.
  }

  async function handleUpdate(values) {
    if (!editingTask) return;
    setSaving(true);
    try {
      const updated = await updateTask(editingTask.id, values);
      afterMutation(updated, updated.id);
      setEditingTask(null);
      setActionError(null);
    } finally {
      setSaving(false);
    }
    // Errors are left to propagate: TaskForm renders them next to the fields.
  }

  async function handleConfirmDelete() {
    if (!pendingDelete) return;
    const target = pendingDelete;

    setDeleting(true);
    try {
      await deleteTask(target.id);
      setTasks((previous) => previous.filter((task) => task.id !== target.id));
      if (editingTask && editingTask.id === target.id) setEditingTask(null);
      setActionError(null);
    } catch (error) {
      setActionError(error);
    } finally {
      setDeleting(false);
      setPendingDelete(null);
    }
  }

  return (
    <div className="dashboard">
      <header className="dashboard__header">
        <div>
          <h1 className="dashboard__title">Your board</h1>
          <p className="dashboard__subtitle">
            Signed in as {user ? user.name : 'you'}
            {!loading && !loadError && stats.total > 0
              ? ` — ${stats.open} open, ${stats.done} done`
              : ''}
          </p>
        </div>

        {!loading && !loadError && stats.overdue > 0 && (
          <p className="dashboard__warning">
            {stats.overdue} {stats.overdue === 1 ? 'task is' : 'tasks are'} overdue
          </p>
        )}
      </header>

      {actionError && (
        <ErrorMessage
          error={actionError}
          title="That did not work"
          onDismiss={() => setActionError(null)}
        />
      )}

      <section className="panel" aria-labelledby="task-form-heading">
        <h2 className="panel__title" id="task-form-heading">
          {editingTask ? 'Edit task' : 'Add a task'}
        </h2>
        {/* Remounting on the selected id is what resets the form fields. */}
        <TaskForm
          key={editingTask ? editingTask.id : 'new'}
          initialValues={editingTask}
          onSubmit={editingTask ? handleUpdate : handleCreate}
          onCancel={editingTask ? () => setEditingTask(null) : undefined}
          submitLabel={editingTask ? 'Save changes' : 'Add task'}
          busy={saving}
        />
      </section>

      <section className="board" aria-labelledby="board-heading">
        <div className="board__toolbar">
          <h2 className="panel__title" id="board-heading">
            Tasks
          </h2>

          <div className="board__filters">
            <div className="field field--inline">
              <label className="sr-only" htmlFor="task-search">
                Search tasks
              </label>
              <input
                id="task-search"
                className="input input--sm"
                type="search"
                placeholder="Search tasks…"
                value={searchInput}
                onChange={(event) => setSearchInput(event.target.value)}
              />
            </div>

            <div className="field field--inline">
              <label className="sr-only" htmlFor="task-status-filter">
                Filter by status
              </label>
              <select
                id="task-status-filter"
                className="input input--sm"
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value)}
              >
                <option value="">All statuses</option>
                <option value="todo">To do</option>
                <option value="in_progress">In progress</option>
                <option value="done">Done</option>
              </select>
            </div>
          </div>
        </div>

        {pendingDelete && (
          <div className="confirm-bar" role="alertdialog" aria-label="Confirm deletion">
            <p className="confirm-bar__text">
              Delete &ldquo;{pendingDelete.title}&rdquo;? This cannot be undone.
            </p>
            <div className="confirm-bar__actions">
              <button
                type="button"
                className="btn btn--danger btn--sm"
                onClick={handleConfirmDelete}
                disabled={deleting}
              >
                {deleting ? 'Deleting…' : 'Delete'}
              </button>
              <button
                type="button"
                className="btn btn--ghost btn--sm"
                onClick={() => setPendingDelete(null)}
                disabled={deleting}
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {loading && <Spinner label="Loading your tasks…" />}

        {!loading && loadError && (
          <div className="board__error">
            <ErrorMessage error={loadError} title="Could not load your tasks" />
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              onClick={() => setReloadToken((token) => token + 1)}
            >
              Try again
            </button>
          </div>
        )}

        {!loading && !loadError && tasks.length === 0 && (
          <div className="empty-state">
            <p className="empty-state__title">
              {filtersActive ? 'Nothing matches those filters' : 'No tasks yet'}
            </p>
            <p className="empty-state__text">
              {filtersActive
                ? 'Try a different status, or clear the search box.'
                : 'Add your first task with the form above.'}
            </p>
          </div>
        )}

        {!loading && !loadError && tasks.length > 0 && (
          <div className="board__grid">
            {tasks.map((task) => (
              <TaskCard
                key={task.id}
                task={task}
                onEdit={setEditingTask}
                onDelete={setPendingDelete}
                busy={deleting}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
