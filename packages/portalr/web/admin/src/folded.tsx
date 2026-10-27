/**
 * A toolbar action (portalr ADR-0081): a button in the row above a table, Invite… or Find…, which
 * opens its form in a card beneath the row, so a page opens on what is there, not on blank
 * fields. In a `Toolbar`, the buttons sit together at the row's end and an open form takes the
 * full line under them. A filter's action says what is in effect beside it while it is closed.
 */

import { Button, Card, SectionTitle } from "@portalr/ui";
import { type ReactNode, useId, useState } from "react";

/** The row above a table that holds its actions: filters at the start, what makes things at the end. */
export function Toolbar({ children }: { children: ReactNode }) {
  return <div className="flex flex-wrap items-center justify-end gap-2">{children}</div>;
}

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
  /** The form's heading, once open; the region's name. */
  title: ReactNode;
  /** The button that opens it: a verb, such as "Invite…" or "Find…". */
  action: string;
  /** What is in effect while it is closed, beside the button: a filter's window, say. */
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
  const [opened, setOpened] = useState(defaultOpen);
  const shown = open ?? opened;
  const toggle = () => {
    setOpened(!shown);
    onOpenChange?.(!shown);
  };
  return (
    <>
      {said && !shown && <span className="text-muted text-xs">{said}</span>}
      <Button
        variant="secondary"
        size="sm"
        aria-expanded={shown}
        aria-controls={id}
        onClick={toggle}
      >
        {action}
      </Button>
      {shown && (
        <Card
          id={id}
          render={<section aria-labelledby={`${id}-title`} />}
          className={
            className
              ? `order-last basis-full flex flex-col gap-3 ${className}`
              : "order-last basis-full flex flex-col gap-3"
          }
        >
          <SectionTitle id={`${id}-title`} {...heading}>
            {title}
          </SectionTitle>
          {children}
        </Card>
      )}
    </>
  );
}
