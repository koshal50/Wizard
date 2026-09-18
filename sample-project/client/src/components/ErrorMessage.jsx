/**
 * Renders an API error.
 *
 * Accepts either an Error produced by the axios interceptors — which carries
 * `message`, `code` and `details` — or a plain string, so a component can also
 * report its own local problems without wrapping them first.
 */
export default function ErrorMessage({ error, title = 'Something went wrong', onDismiss }) {
  if (!error) return null;

  const message = typeof error === 'string' ? error : error.message;
  const details = typeof error === 'object' && Array.isArray(error.details) ? error.details : [];

  return (
    <div className="alert alert--error" role="alert">
      <div className="alert__body">
        <strong className="alert__title">{title}</strong>
        <p className="alert__message">{message}</p>

        {details.length > 0 && (
          <ul className="alert__details">
            {details.map((detail) => (
              <li key={`${detail.field}:${detail.message}`}>{detail.message}</li>
            ))}
          </ul>
        )}
      </div>

      {onDismiss && (
        <button type="button" className="alert__close" onClick={onDismiss} aria-label="Dismiss">
          &times;
        </button>
      )}
    </div>
  );
}
