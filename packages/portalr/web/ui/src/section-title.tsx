import type { ReactNode } from "react";

/** A section's heading, under the page's one: the same size and weight wherever a page has one. */
export function SectionTitle({ id, children }: { id?: string; children: ReactNode }) {
  return (
    <h2 id={id} className="font-bold text-fg text-lg tracking-tight">
      {children}
    </h2>
  );
}
