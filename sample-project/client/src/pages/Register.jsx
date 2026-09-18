import { useState } from 'react';
import { Link, Navigate } from 'react-router-dom';

import ErrorMessage from '../components/ErrorMessage.jsx';
import { useAuth } from '../context/AuthContext.jsx';

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

const MIN_PASSWORD_LENGTH = 8;

export default function Register() {
  const { register, isAuthenticated } = useAuth();

  const [values, setValues] = useState({
    name: '',
    email: '',
    password: '',
    confirmPassword: '',
  });
  const [fieldErrors, setFieldErrors] = useState({});
  const [formError, setFormError] = useState(null);
  const [busy, setBusy] = useState(false);

  if (isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  function updateField(field, value) {
    setValues((previous) => ({ ...previous, [field]: value }));
    setFieldErrors((previous) =>
      previous[field] ? { ...previous, [field]: undefined } : previous
    );
  }

  function validate() {
    const errors = {};
    const email = values.email.trim();

    if (!values.name.trim()) errors.name = 'Name is required.';
    if (!email) errors.email = 'Email is required.';
    else if (!EMAIL_PATTERN.test(email)) errors.email = 'Enter a valid email address.';

    if (!values.password) errors.password = 'Password is required.';
    else if (values.password.length < MIN_PASSWORD_LENGTH) {
      errors.password = `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`;
    }

    // Checked here only: the server never sees this field.
    if (values.confirmPassword !== values.password) {
      errors.confirmPassword = 'Passwords do not match.';
    }

    return errors;
  }

  async function handleSubmit(event) {
    event.preventDefault();

    const errors = validate();
    setFieldErrors(errors);
    if (Object.keys(errors).length > 0) return;

    setBusy(true);
    setFormError(null);

    try {
      await register({
        name: values.name.trim(),
        email: values.email.trim(),
        password: values.password,
      });
    } catch (error) {
      setFormError(error);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <header className="auth-card__header">
          <span className="auth-card__mark" aria-hidden="true" />
          <h1 className="auth-card__title">Create your board</h1>
          <p className="auth-card__subtitle">One account, one private board of tasks.</p>
        </header>

        <ErrorMessage error={formError} title="Could not create your account" />

        <form className="auth-form" onSubmit={handleSubmit} noValidate>
          <div className="field">
            <label className="field__label" htmlFor="register-name">
              Name
            </label>
            <input
              id="register-name"
              name="name"
              autoComplete="name"
              className={fieldErrors.name ? 'input input--invalid' : 'input'}
              value={values.name}
              onChange={(event) => updateField('name', event.target.value)}
            />
            {fieldErrors.name && <p className="field__error">{fieldErrors.name}</p>}
          </div>

          <div className="field">
            <label className="field__label" htmlFor="register-email">
              Email
            </label>
            <input
              id="register-email"
              name="email"
              type="email"
              autoComplete="email"
              className={fieldErrors.email ? 'input input--invalid' : 'input'}
              value={values.email}
              onChange={(event) => updateField('email', event.target.value)}
            />
            {fieldErrors.email && <p className="field__error">{fieldErrors.email}</p>}
          </div>

          <div className="field">
            <label className="field__label" htmlFor="register-password">
              Password
            </label>
            <input
              id="register-password"
              name="password"
              type="password"
              autoComplete="new-password"
              className={fieldErrors.password ? 'input input--invalid' : 'input'}
              value={values.password}
              onChange={(event) => updateField('password', event.target.value)}
              aria-describedby="register-password-hint"
            />
            <p className="field__hint" id="register-password-hint">
              At least {MIN_PASSWORD_LENGTH} characters.
            </p>
            {fieldErrors.password && <p className="field__error">{fieldErrors.password}</p>}
          </div>

          <div className="field">
            <label className="field__label" htmlFor="register-confirm-password">
              Confirm password
            </label>
            <input
              id="register-confirm-password"
              name="confirmPassword"
              type="password"
              autoComplete="new-password"
              className={fieldErrors.confirmPassword ? 'input input--invalid' : 'input'}
              value={values.confirmPassword}
              onChange={(event) => updateField('confirmPassword', event.target.value)}
            />
            {fieldErrors.confirmPassword && (
              <p className="field__error">{fieldErrors.confirmPassword}</p>
            )}
          </div>

          <button type="submit" className="btn btn--primary btn--block" disabled={busy}>
            {busy ? 'Creating your board…' : 'Create account'}
          </button>
        </form>

        <p className="auth-card__footer">
          Already registered? <Link to="/login">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
