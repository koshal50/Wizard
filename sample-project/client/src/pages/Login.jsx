import { useState } from 'react';
import { Link, Navigate, useLocation } from 'react-router-dom';

import ErrorMessage from '../components/ErrorMessage.jsx';
import { useAuth } from '../context/AuthContext.jsx';

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function Login() {
  const { login, isAuthenticated } = useAuth();
  const location = useLocation();

  const [values, setValues] = useState({ email: '', password: '' });
  const [fieldErrors, setFieldErrors] = useState({});
  const [formError, setFormError] = useState(null);
  const [busy, setBusy] = useState(false);

  // Where to go after signing in: back to the page that bounced us here, if any.
  const redirectTo = (location.state && location.state.from) || '/';

  if (isAuthenticated) {
    return <Navigate to={redirectTo} replace />;
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

    if (!email) errors.email = 'Email is required.';
    else if (!EMAIL_PATTERN.test(email)) errors.email = 'Enter a valid email address.';

    if (!values.password) errors.password = 'Password is required.';

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
      await login({ email: values.email.trim(), password: values.password });
      // No navigation here: the auth state flips and the redirect above runs.
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
          <h1 className="auth-card__title">Welcome back</h1>
          <p className="auth-card__subtitle">Sign in to open your board.</p>
        </header>

        <ErrorMessage error={formError} title="Could not sign you in" />

        <form className="auth-form" onSubmit={handleSubmit} noValidate>
          <div className="field">
            <label className="field__label" htmlFor="login-email">
              Email
            </label>
            <input
              id="login-email"
              name="email"
              type="email"
              autoComplete="email"
              className={fieldErrors.email ? 'input input--invalid' : 'input'}
              value={values.email}
              onChange={(event) => updateField('email', event.target.value)}
              aria-invalid={Boolean(fieldErrors.email)}
              aria-describedby={fieldErrors.email ? 'login-email-error' : undefined}
            />
            {fieldErrors.email && (
              <p className="field__error" id="login-email-error">
                {fieldErrors.email}
              </p>
            )}
          </div>

          <div className="field">
            <label className="field__label" htmlFor="login-password">
              Password
            </label>
            <input
              id="login-password"
              name="password"
              type="password"
              autoComplete="current-password"
              className={fieldErrors.password ? 'input input--invalid' : 'input'}
              value={values.password}
              onChange={(event) => updateField('password', event.target.value)}
              aria-invalid={Boolean(fieldErrors.password)}
              aria-describedby={fieldErrors.password ? 'login-password-error' : undefined}
            />
            {fieldErrors.password && (
              <p className="field__error" id="login-password-error">
                {fieldErrors.password}
              </p>
            )}
          </div>

          <button type="submit" className="btn btn--primary btn--block" disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <p className="auth-card__footer">
          No account yet? <Link to="/register">Create one</Link>
        </p>
      </div>
    </div>
  );
}
