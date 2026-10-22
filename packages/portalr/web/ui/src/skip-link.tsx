/**
 * The link past the frame to the page's content, the first thing the keyboard reaches: hidden
 * until it is focused, then a bar across the top of the frame in a room of its own, which moves
 * the frame down rather than covering the mark. Security chrome, which a brand kit doesn't
 * restyle (lattice RFC-0007).
 */
export function SkipLink() {
  return (
    <a
      href="#main"
      className="sr-only bg-surface font-semibold text-sm focus:not-sr-only focus:col-span-full focus:block focus:px-3 focus:py-2 focus-visible:outline-(length:--focus-width) focus-visible:outline-focus focus-visible:-outline-offset-(--focus-width)"
    >
      Skip to content
    </a>
  );
}
