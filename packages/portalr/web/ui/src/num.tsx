/**
 * A figure as text, its digits tabular so that figures in a column line up, and nothing else:
 * Schibsted Grotesk's tabular set also widens its decimal point, comma, colon and percent sign to
 * the width of a digit, which sets "$60.40" as "$60 . 40". So each run of digits wears
 * `tabular-nums`, and the punctuation between them keeps its own width.
 */
export function Num({ children }: { children: string }) {
  return [...children.matchAll(/(\d+)|\D+/g)].map((part) =>
    part[1] ? (
      <span key={part.index} className="tabular-nums">
        {part[0]}
      </span>
    ) : (
      part[0]
    ),
  );
}
