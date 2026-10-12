import type { ReactNode } from "react";

/** A page: its title, as the page's one heading, and what it holds. */
export function Page({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <main>
      <h1>{title}</h1>
      {children}
    </main>
  );
}
