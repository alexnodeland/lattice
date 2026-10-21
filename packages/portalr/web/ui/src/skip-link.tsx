/**
 * The link past the frame to the page's content, the first thing the keyboard reaches: hidden
 * until it is focused. Security chrome, which a brand kit doesn't restyle (lattice RFC-0007).
 */
export function SkipLink() {
  return (
    <a
      href="#main"
      className="fixed top-2 left-2 z-50 -translate-y-16 rounded-md bg-surface px-3 py-2 font-semibold text-sm focus:translate-y-0 focus-visible:outline-(length:--focus-width) focus-visible:outline-focus"
    >
      Skip to content
    </a>
  );
}
