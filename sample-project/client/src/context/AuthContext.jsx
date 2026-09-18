import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import api, {
  clearStoredSession,
  getStoredRefreshToken,
  getStoredToken,
  setUnauthorizedHandler,
  storeSession,
} from '../api/client.js';

/**
 * Session state for the whole app.
 *
 * The access token lives in localStorage so a reload does not sign the user out.
 * That is a deliberate trade-off: it is readable by any script on the page, so
 * the token is short-lived and a stolen one can be revoked server side. Keeping
 * it in memory only would be stricter but would log the user out on every
 * refresh.
 */

const AuthContext = createContext(null);

const STATUS = {
  loading: 'loading',
  authenticated: 'authenticated',
  anonymous: 'anonymous',
};

const USER_KEY = 'taskboard.user';

function readStoredUser() {
  try {
    const raw = window.localStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function AuthProvider({ children }) {
  const navigate = useNavigate();
  const [user, setUser] = useState(readStoredUser);
  // A stored token is only a claim; it is verified against /auth/me below, so
  // start in `loading` and let the request settle it.
  const [status, setStatus] = useState(() =>
    getStoredToken() ? STATUS.loading : STATUS.anonymous
  );

  // Restore the session on first mount.
  useEffect(() => {
    if (!getStoredToken()) return undefined;

    let cancelled = false;

    (async () => {
      try {
        const response = await api.get('/auth/me');
        if (cancelled) return;
        setUser(response.data.data.user);
        setStatus(STATUS.authenticated);
      } catch {
        if (cancelled) return;
        clearStoredSession();
        setUser(null);
        setStatus(STATUS.anonymous);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  // The API rejected our token: drop the session and send the user to log in.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      setUser(null);
      setStatus(STATUS.anonymous);
      navigate('/login', { replace: true });
    });
    return () => setUnauthorizedHandler(null);
  }, [navigate]);

  const login = useCallback(async (credentials) => {
    const response = await api.post('/auth/login', credentials);
    const session = response.data.data;
    storeSession(session);
    setUser(session.user);
    setStatus(STATUS.authenticated);
    return session.user;
  }, []);

  const register = useCallback(async (input) => {
    const response = await api.post('/auth/register', input);
    const session = response.data.data;
    storeSession(session);
    setUser(session.user);
    setStatus(STATUS.authenticated);
    return session.user;
  }, []);

  const logout = useCallback(async () => {
    const refreshToken = getStoredRefreshToken();
    try {
      // Revoking server side is what makes this more than forgetting a string.
      await api.post('/auth/logout', refreshToken ? { refreshToken } : {});
    } catch {
      // A failed round trip must not trap the user in a session they asked to end.
    } finally {
      clearStoredSession();
      setUser(null);
      setStatus(STATUS.anonymous);
    }
  }, []);

  const value = useMemo(
    () => ({
      user,
      status,
      isAuthenticated: status === STATUS.authenticated,
      isLoading: status === STATUS.loading,
      login,
      register,
      logout,
    }),
    [user, status, login, register, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider.');
  }
  return context;
}

export { STATUS as AUTH_STATUS };
