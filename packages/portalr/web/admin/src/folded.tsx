/**
 * A card whose contents fold behind a line (portalr ADR-0080): a form that makes something, closed
 * until it is wanted, so a page opens on what is there, not on blank fields; or a filter bar, open
 * while something is set, and otherwise closed with what is in effect said on the line.
 */

import { Card, Disclosure, SectionTitle } from "@portalr/ui";
import { type ReactNode, useId } from "react";

export function Folded({
  title,
  action,
  said,
  defaultOpen = false,
  open,
  onOpenChange,
  heading,
  className,
  children,
}: {
  /** The section's heading. */
  title: ReactNode;
  /** The line that opens it: a verb, such as "Invite…" or "Find…". */
  action: string;
  /** What is in effect while it is closed, beside the line: a filter's window, say. */
  said?: string | null;
  defaultOpen?: boolean;
  /** Open or not, where the page holds it. */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** The heading's props, where the page focuses it. */
  heading?: { ref: React.Ref<HTMLHeadingElement>; tabIndex: -1 };
  className?: string;
  children: ReactNode;
}) {
  const id = useId();
  return (
    <Card
      render={<section aria-labelledby={id} />}
      className={className ? `flex flex-col gap-3 ${className}` : "flex flex-col gap-3"}
    >
      <SectionTitle id={id} {...heading}>
        {title}
      </SectionTitle>
      <Disclosure
        summary={
          <span className="flex flex-wrap items-baseline gap-x-2">
            {action}
            {said && <span className="text-muted text-xs">{said}</span>}
          </span>
        }
        defaultOpen={defaultOpen}
        {...(open !== undefined && { open })}
        {...(onOpenChange && { onOpenChange })}
        panelClassName="flex flex-col gap-3 pt-3"
      >
        {children}
      </Disclosure>
    </Card>
  );
}
