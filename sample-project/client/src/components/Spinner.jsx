/**
 * A small, accessible loading indicator.
 *
 * `role="status"` with `aria-live` means screen readers announce the label when
 * it appears, and the ring is decorative so it is hidden from the accessibility
 * tree.
 */
export default function Spinner({ label = 'Loading…' }) {
  return (
    <div className="spinner" role="status" aria-live="polite">
      <span className="spinner__ring" aria-hidden="true" />
      <span className="spinner__label">{label}</span>
    </div>
  );
}
