import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * The axios instance is mocked so submitting a valid form never touches the
 * network; these tests are about the form's own behaviour and the calls it makes.
 */
vi.mock('../../api/client.js', () => ({
  default: { get: vi.fn(), post: vi.fn() },
  getStoredToken: () => null,
  getStoredRefreshToken: () => null,
  storeSession: vi.fn(),
  clearStoredSession: vi.fn(),
  setUnauthorizedHandler: vi.fn(),
}));

import api from '../../api/client.js';
import { AuthProvider } from '../../context/AuthContext.jsx';
import Login from '../Login.jsx';

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={['/login']}>
      <AuthProvider>
        <Login />
      </AuthProvider>
    </MemoryRouter>
  );
}

/**
 * Submit the form directly rather than clicking the button: it exercises the
 * onSubmit handler without depending on jsdom's form-activation behaviour.
 */
function submitForm() {
  const form = screen.getByRole('button', { name: 'Sign in' }).closest('form');
  fireEvent.submit(form);
}

describe('Login', () => {
  beforeEach(() => {
    api.post.mockReset();
  });

  it('reports every empty field and sends nothing', () => {
    renderLogin();

    submitForm();

    expect(screen.getByText('Email is required.')).toBeInTheDocument();
    expect(screen.getByText('Password is required.')).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('rejects an email that is not an address', () => {
    renderLogin();

    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'not-an-email' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'secret-pass' } });
    submitForm();

    expect(screen.getByText('Enter a valid email address.')).toBeInTheDocument();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('clears a field error as soon as it is corrected', () => {
    renderLogin();

    submitForm();
    expect(screen.getByText('Email is required.')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'ada@example.com' } });

    expect(screen.queryByText('Email is required.')).not.toBeInTheDocument();
  });

  it('posts trimmed credentials when the form is valid', async () => {
    api.post.mockResolvedValue({
      data: {
        data: {
          user: { id: 'user-1', email: 'ada@example.com', name: 'Ada' },
          accessToken: 'access-token',
          refreshToken: 'refresh-token',
        },
      },
    });

    renderLogin();

    fireEvent.change(screen.getByLabelText('Email'), { target: { value: '  ada@example.com  ' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'secret-pass' } });
    submitForm();

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith('/auth/login', {
        email: 'ada@example.com',
        password: 'secret-pass',
      });
    });
  });

  it('shows the message the API returned when the credentials are wrong', async () => {
    api.post.mockRejectedValue(
      Object.assign(new Error('Email or password is incorrect.'), {
        code: 'INVALID_CREDENTIALS',
        status: 401,
        details: [],
      })
    );

    renderLogin();

    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'ada@example.com' } });
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'wrong-password' } });
    submitForm();

    expect(await screen.findByRole('alert')).toHaveTextContent('Email or password is incorrect.');
  });

  it('offers a link to the registration page', () => {
    renderLogin();

    expect(screen.getByRole('link', { name: 'Create one' })).toHaveAttribute('href', '/register');
  });
});
