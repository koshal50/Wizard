import { Navigate, useLocation } from 'react-router-dom';

import { AUTH_STATUS, useAuth } from '../context/AuthContext.jsx';
import Spinner from './Spinner.jsx';

/**
 * Gate for routes that need a session.
 *
 * While the stored token is being verified the answer is unknown, so the
 * alternative is a spinner rather than a redirect — sending the user to /login
 * and bouncing them back a moment later is worse than a brief wait.
 */
export default function ProtectedRoute({ children }) {
  const { status } = useAuth();
  const location = useLocation();

  if (status === AUTH_STATUS.loading) {
    return <Spinner label="Checking your session…" />;
  }

  if (status !== AUTH_STATUS.authenticated) {
    // `from` lets the login page send the user back where they were headed.
    return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  }

  return children;
}
