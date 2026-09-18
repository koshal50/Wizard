import axios from 'axios';

/**
 * The single axios instance every request goes through.
 *
 * Two interceptors do the work: one attaches the bearer token, the other turns
 * an API error envelope into a plain Error the components can render, and pulls
 * the plug on a session the server has already rejected.
 */

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:4000/api';

const STORAGE_KEYS = {
  accessToken: 'taskboard.accessToken',
  refreshToken: 'taskboard.refreshToken',
  user: 'taskboard.user',
};

/**
 * localStorage throws in a few real situations (Safari private browsing, storage
 * disabled by policy). None of them should break the app, so every access is
 * guarded and a failure just means "no stored session".
 */
function read(key) {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key, value) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* nothing we can do; the session simply will not survive a reload */
  }
}

function remove(key) {
  try {
    window.localStorage.removeItem(key);
  } catch {
    /* as above */
  }
}

export function getStoredToken() {
  return read(STORAGE_KEYS.accessToken);
}

export function getStoredRefreshToken() {
  return read(STORAGE_KEYS.refreshToken);
}

/** Persist a session returned by register, login or refresh. */
export function storeSession(session) {
  write(STORAGE_KEYS.accessToken, session.accessToken);
  if (session.refreshToken) write(STORAGE_KEYS.refreshToken, session.refreshToken);
  if (session.user) write(STORAGE_KEYS.user, JSON.stringify(session.user));
}

export function clearStoredSession() {
  remove(STORAGE_KEYS.accessToken);
  remove(STORAGE_KEYS.refreshToken);
  remove(STORAGE_KEYS.user);
}

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
});

api.interceptors.request.use((config) => {
  const token = getStoredToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

/**
 * Called when the API rejects a session, so the auth context can drop its state
 * and send the user to the login page. Assigned by AuthContext at mount; kept as
 * a callback rather than an import so the two modules do not depend on each
 * other in a circle.
 */
let onUnauthorized = null;

export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler;
}

/**
 * Requests that are *expected* to answer 401: a wrong password is a normal
 * outcome, not an expired session, and must not bounce the user to /login while
 * they are already there.
 */
function isCredentialRequest(url = '') {
  return url.includes('/auth/login') || url.includes('/auth/register');
}

/** Give every rejection the same shape: message, status, code, details. */
function normaliseError(error) {
  if (!error.response) {
    const message =
      error.code === 'ECONNABORTED'
        ? 'The server took too long to respond.'
        : 'Could not reach the server. Check that the API is running.';
    return Object.assign(new Error(message), { code: 'NETWORK_ERROR', status: 0, details: [] });
  }

  const { status, data } = error.response;
  const payload = data && data.error ? data.error : {};

  return Object.assign(new Error(payload.message || `Request failed with status ${status}.`), {
    status,
    code: payload.code || 'UNKNOWN_ERROR',
    details: payload.details || [],
  });
}

api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response && error.response.status;
    const url = (error.config && error.config.url) || '';

    if (status === 401 && !isCredentialRequest(url)) {
      clearStoredSession();
      if (onUnauthorized) onUnauthorized();
    }

    return Promise.reject(normaliseError(error));
  }
);

export default api;
