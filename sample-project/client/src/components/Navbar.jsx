import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { useAuth } from '../context/AuthContext.jsx';

/** Top bar. Only rendered for signed-in users — see App.jsx. */
export default function Navbar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [signingOut, setSigningOut] = useState(false);

  async function handleSignOut() {
    setSigningOut(true);
    try {
      await logout();
    } finally {
      setSigningOut(false);
      navigate('/login', { replace: true });
    }
  }

  return (
    <header className="navbar">
      <div className="navbar__inner">
        <Link to="/" className="navbar__brand">
          <span className="navbar__mark" aria-hidden="true" />
          Taskboard
        </Link>

        <div className="navbar__user">
          {user && (
            <span className="navbar__name" title={user.email}>
              {user.name}
            </span>
          )}
          <button
            type="button"
            className="btn btn--ghost btn--sm"
            onClick={handleSignOut}
            disabled={signingOut}
          >
            {signingOut ? 'Signing out…' : 'Sign out'}
          </button>
        </div>
      </div>
    </header>
  );
}
