import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import ProtectedRoute from '../ProtectedRoute.jsx';
import { AuthProvider } from '../../context/AuthContext.jsx';

/**
 * The API client is replaced wholesale here: a stored token makes the provider
 * call /auth/me, and the point of these tests is the routing decision, not the
 * HTTP layer. Mocking it keeps axios and a real network out of the way.
 */
vi.mock('../../api/client.js', () => ({
  default: { get: vi.fn(), post: vi.fn() },
  getStoredToken: () => window.localStorage.getItem('taskboard.accessToken'),
  getStoredRefreshToken: () => window.localStorage.getItem('taskboard.refreshToken'),
  storeSession: vi.fn(),
  clearStoredSession: () => window.localStorage.clear(),
  setUnauthorizedHandler: vi.fn(),
}));

import api from '../../api/client.js';

function renderAt(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<p>Sign in to continue</p>} />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <p>Private board</p>
              </ProtectedRoute>
            }
          />
        </Routes>
      </AuthProvider>
    </MemoryRouter>
  );
}

function storeToken() {
  window.localStorage.setItem('taskboard.accessToken', 'stored-token');
}

describe('ProtectedRoute', () => {
  beforeEach(() => {
    api.get.mockReset();
  });

  it('redirects to the login page when there is no session', async () => {
    renderAt('/');

    expect(await screen.findByText('Sign in to continue')).toBeInTheDocument();
    expect(screen.queryByText('Private board')).not.toBeInTheDocument();
    // No token means nothing to verify, so no request is made.
    expect(api.get).not.toHaveBeenCalled();
  });

  it('waits for the stored token to be verified instead of redirecting', async () => {
    storeToken();
    // A request that never settles keeps the provider in its loading state.
    api.get.mockReturnValue(new Promise(() => {}));

    renderAt('/');

    expect(await screen.findByRole('status')).toHaveTextContent('Checking your session');
    expect(screen.queryByText('Sign in to continue')).not.toBeInTheDocument();
  });

  it('renders the protected content once the session is confirmed', async () => {
    storeToken();
    api.get.mockResolvedValue({
      data: {
        data: {
          user: { id: 'user-1', email: 'ada@example.com', name: 'Ada' },
        },
      },
    });

    renderAt('/');

    expect(await screen.findByText('Private board')).toBeInTheDocument();
    expect(api.get).toHaveBeenCalledWith('/auth/me');
  });

  it('redirects when the stored token turns out to be rejected', async () => {
    storeToken();
    api.get.mockRejectedValue(Object.assign(new Error('expired'), { status: 401 }));

    renderAt('/');

    expect(await screen.findByText('Sign in to continue')).toBeInTheDocument();
    // The rejected session is discarded rather than retried on every render.
    expect(window.localStorage.getItem('taskboard.accessToken')).toBeNull();
  });
});
