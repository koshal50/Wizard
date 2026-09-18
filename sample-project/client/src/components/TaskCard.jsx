const STATUS_LABELS = {
  todo: 'To do',
  in_progress: 'In progress',
  done: 'Done',
};

const PRIORITY_LABELS = {
  low: 'Low',
  medium: 'Medium',
  high: 'High',
};

/** 'YYYY-MM-DD' -> '31 Jan 2030'. Parsed as UTC so the day cannot shift. */
function formatDate(value) {
  const date = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  });
}

/** A task is overdue until it is done — a finished task is never late. */
function isOverdue(task) {
  if (!task.dueDate || task.status === 'done') return false;
  const today = new Date().toISOString().slice(0, 10);
  return task.dueDate < today;
}

/**
 * One task, rendered as a card.
 *
 * Presentational on purpose: editing and deleting are the parent's job, so the
 * card can be reused anywhere without dragging state along with it.
 */
export default function TaskCard({ task, onEdit, onDelete, busy = false }) {
  const overdue = isOverdue(task);

  return (
    <article className={`task-card task-card--${task.status}`}>
      <header className="task-card__header">
        <h3 className="task-card__title">{task.title}</h3>
        <span className={`badge badge--priority-${task.priority}`}>
          {PRIORITY_LABELS[task.priority] || task.priority}
        </span>
      </header>

      {task.description && <p className="task-card__description">{task.description}</p>}

      <div className="task-card__meta">
        <span className={`badge badge--status-${task.status}`}>
          {STATUS_LABELS[task.status] || task.status}
        </span>

        {task.dueDate && (
          <span className={overdue ? 'task-card__due task-card__due--overdue' : 'task-card__due'}>
            {overdue ? 'Overdue — ' : 'Due '}
            {formatDate(task.dueDate)}
          </span>
        )}
      </div>

      <footer className="task-card__actions">
        <button
          type="button"
          className="btn btn--ghost btn--sm"
          onClick={() => onEdit(task)}
          disabled={busy}
        >
          Edit
        </button>
        <button
          type="button"
          className="btn btn--danger-ghost btn--sm"
          onClick={() => onDelete(task)}
          disabled={busy}
        >
          Delete
        </button>
      </footer>
    </article>
  );
}
