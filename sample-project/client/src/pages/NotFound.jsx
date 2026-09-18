import { Link } from 'react-router-dom';

export default function NotFound() {
  return (
    <div className="empty-page">
      <p className="empty-page__code">404</p>
      <h1 className="empty-page__title">This page does not exist</h1>
      <p className="empty-page__text">
        The link may be out of date, or the address may have a typo in it.
      </p>
      <Link className="btn btn--primary" to="/">
        Back to the board
      </Link>
    </div>
  );
}
