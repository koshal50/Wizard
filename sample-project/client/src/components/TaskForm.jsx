import { useState } from 'react';

import ErrorMessage from './ErrorMessage.jsx';

const EMPTY_VALUES = {
  title: '',
  description: '',
  status: 'todo',
  priority: 'medium',
  dueDate: '',
};

const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/;

function toFormValues(task) {
  if (!task) return EMPTY_VALUES;
  return {
    title: task.title || '',
    description: task.description || '',
    status: task.status || 'todo',
    priority: task.priority || 'medium',
    // The API speaks YYYY-MM-DD, which is exactly what <input type="date"> uses.
    dueDate: task.dueDate || '',
  };
}

/**
 * Create/edit form for a task.
 *
 * Client-side validation mirrors the server's rules for the obvious cases so the
 * user gets an answer without a round trip; the server still validates, because
 * this one can be bypassed.
 *
 * The parent remounts this component with a `key` when the task being edited
 * changes, which is why there is no effect syncing props into state.
 */
export default function TaskForm({
  initialValues,
  onSubmit,
  onCancel,
  submitLabel = 'Add task',
  busy = false,
}) {
  const isEditing = Boolean(initialValues);
  const [values, setValues] = useState(() => toFormValues(initialValues));
  const [fieldErrors, setFieldErrors] = useState({});
  const [formError, setFormError] = useState(null);

  function updateField(field, value) {
    setValues((previous) => ({ ...previous, [field]: value }));
    // Clear the error as soon as the user starts fixing it.
    setFieldErrors((previous) => (previous[field] ? { ...previous, [field]: undefined } : previous));
  }

  function validate() {
    const errors = {};
    const title = values.title.trim();

    if (!title) errors.title = 'Title is required.';
    else if (title.length > 200) errors.title = 'Title must be at most 200 characters.';

    if (values.description.trim().length > 2000) {
      errors.description = 'Description must be at most 2000 characters.';
    }

    if (values.dueDate && !DATE_ONLY.test(values.dueDate)) {
      errors.dueDate = 'Pick a valid date.';
    }

    return errors;
  }

  async function handleSubmit(event) {
    event.preventDefault();

    const errors = validate();
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;

    setFormError(null);

    try {
      await onSubmit({
        title: values.title.trim(),
        // Empty inputs mean "no description / no due date" — the API clears a
        // field when it is sent as null.
        description: values.description.trim() || null,
        status: values.status,
        priority: values.priority,
        dueDate: values.dueDate || null,
      });

      if (!isEditing) {
        setValues(EMPTY_VALUES);
      }
    } catch (error) {
      setFormError(error);
    }
  }

  return (
    <form className="task-form" onSubmit={handleSubmit} noValidate>
      <ErrorMessage error={formError} title="Could not save the task" />

      <div className="field">
        <label className="field__label" htmlFor="task-title">
          Title
        </label>
        <input
          id="task-title"
          className={fieldErrors.title ? 'input input--invalid' : 'input'}
          value={values.title}
          onChange={(event) => updateField('title', event.target.value)}
          placeholder="What needs doing?"
          maxLength={200}
          aria-invalid={Boolean(fieldErrors.title)}
          aria-describedby={fieldErrors.title ? 'task-title-error' : undefined}
        />
        {fieldErrors.title && (
          <p className="field__error" id="task-title-error">
            {fieldErrors.title}
          </p>
        )}
      </div>

      <div className="field">
        <label className="field__label" htmlFor="task-description">
          Notes <span className="field__hint">optional</span>
        </label>
        <textarea
          id="task-description"
          className={fieldErrors.description ? 'input input--invalid' : 'input'}
          value={values.description}
          onChange={(event) => updateField('description', event.target.value)}
          rows={3}
          placeholder="Anything worth remembering about this task."
          maxLength={2000}
        />
        {fieldErrors.description && <p className="field__error">{fieldErrors.description}</p>}
      </div>

      <div className="task-form__row">
        <div className="field">
          <label className="field__label" htmlFor="task-status">
            Status
          </label>
          <select
            id="task-status"
            className="input"
            value={values.status}
            onChange={(event) => updateField('status', event.target.value)}
          >
            <option value="todo">To do</option>
            <option value="in_progress">In progress</option>
            <option value="done">Done</option>
          </select>
        </div>

        <div className="field">
          <label className="field__label" htmlFor="task-priority">
            Priority
          </label>
          <select
            id="task-priority"
            className="input"
            value={values.priority}
            onChange={(event) => updateField('priority', event.target.value)}
          >
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
          </select>
        </div>

        <div className="field">
          <label className="field__label" htmlFor="task-due-date">
            Due date <span className="field__hint">optional</span>
          </label>
          <input
            id="task-due-date"
            type="date"
            className={fieldErrors.dueDate ? 'input input--invalid' : 'input'}
            value={values.dueDate}
            onChange={(event) => updateField('dueDate', event.target.value)}
          />
          {fieldErrors.dueDate && <p className="field__error">{fieldErrors.dueDate}</p>}
        </div>
      </div>

      <div className="task-form__actions">
        <button type="submit" className="btn btn--primary" disabled={busy}>
          {busy ? 'Saving…' : submitLabel}
        </button>

        {onCancel && (
          <button type="button" className="btn btn--ghost" onClick={onCancel} disabled={busy}>
            Cancel
          </button>
        )}
      </div>
    </form>
  );
}
