/**
 * The mountain mark from the tracker's toolbar, as a standalone piece so the
 * public pages and the app cannot drift apart.
 */
export function Wordmark() {
  return (
    <>
      <svg className="wordmark-mark" viewBox="0 0 28 20" aria-hidden="true">
        <path d="M2 18 L10 4 L15 12 L18.5 7 L26 18 Z" fill="currentColor" />
      </svg>
      <span className="wordmark-text">
        PIT <b>BOX</b>
      </span>
    </>
  )
}
