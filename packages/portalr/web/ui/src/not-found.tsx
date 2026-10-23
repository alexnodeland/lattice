import type { ReactNode } from "react";
import { PageHeader } from "./page-header";

/**
 * A page that isn't there, in the frame (portalr ADR-0068): its heading names what is missing,
 * as the window's title does, and takes the focus; a sentence says why it may be; and one link
 * leads on. It stands in for the page, as a page's own `h1` would.
 */
export function NotFound({
  title,
  children,
  action,
}: {
  /** What is missing, such as "Artifact not found". */
  title: string;
  /** Why it may be, in a sentence. */
  children: ReactNode;
  /** The one way on, such as a link to the list it would be in. */
  action: ReactNode;
}) {
  return (
    <>
      <PageHeader title={title} focus />
      <p className="text-muted">{children}</p>
      <div>{action}</div>
    </>
  );
}
