/**
 * A toolbar action (portalr ADR-0081): a button in the row above a table, Invite… or Find…, which
 * opens its form in a card beneath the row, so a page opens on what is there, not on blank
 * fields. A `Toolbar` holds the buttons together at the row's end, and the open forms in a row
 * of their own beneath, in the order of their buttons, so what is read follows what is seen. As a
 * form opens its first field takes the focus; Escape closes it and the focus comes back to its
 * button. A filter's action says what is in effect beside it while it is closed.
 */

import { Button, Card, SectionTitle } from "@portalr/ui";
import {
  createContext,
  type KeyboardEvent,
  type ReactNode,
  useContext,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";

/** Where a toolbar's open forms go: the row beneath its buttons. */
const Beneath = createContext<HTMLDivElement | null>(null);

/**
 * The row above a table that holds its actions, and beneath it the forms they open. The row
 * beneath is an element made once, so a form opens into it on the first render and never moves
 * (a move would drop the focus a page put on its heading).
 */
export function Toolbar({ children }: { children: ReactNode }) {
  const [beneath] = useState(() => {
    const row = document.createElement("div");
    row.className = "flex flex-col gap-3 empty:hidden";
    return row;
  });
  return (
    <Beneath value={beneath}>
      <div className="flex flex-col gap-3 empty:hidden">
        <div className="flex flex-wrap items-center justify-end gap-2 empty:hidden">{children}</div>
        <div
          // Attached once: moving it again would drop the focus from a field inside it.
          ref={(node) => {
            if (node && beneath.parentNode !== node) {
              node.append(beneath);
            }
          }}
          className="contents"
        />
      </div>
    </Beneath>
  );
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
  /** The heading's props, where the page focuses it instead of the first field. */
  heading?: { ref: React.Ref<HTMLHeadingElement>; tabIndex: -1 };
  className?: string;
  children: ReactNode;
}) {
  const id = useId();
  const beneath = useContext(Beneath);
  const trigger = useRef<HTMLButtonElement>(null);
  const card = useRef<HTMLDivElement>(null);
  const [opened, setOpened] = useState(defaultOpen);
  const shown = open ?? opened;
  const show = (next: boolean) => {
    setOpened(next);
    onOpenChange?.(next);
  };
  // Opened by its button, the form's first field takes the focus; the page's own focus wins.
  const [byButton, setByButton] = useState(false);
  useEffect(() => {
    if (shown && byButton && !heading) {
      card.current
        ?.querySelector<HTMLElement>("input, select, textarea, [role=combobox], button")
        ?.focus();
    }
  }, [shown, byButton, heading]);
  const closeOnEscape = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape" && !event.defaultPrevented) {
      event.preventDefault();
      show(false);
      trigger.current?.focus();
    }
  };
  const panel = shown && (
    <Card
      ref={card}
      id={id}
      render={<section aria-labelledby={`${id}-title`} />}
      className={className ? `flex flex-col gap-3 ${className}` : "flex flex-col gap-3"}
      onKeyDown={closeOnEscape}
    >
      <SectionTitle id={`${id}-title`} {...heading}>
        {title}
      </SectionTitle>
      {children}
    </Card>
  );
  return (
    <>
      {said && !shown && <span className="text-muted text-xs">{said}</span>}
      <Button
        ref={trigger}
        variant="secondary"
        size="sm"
        aria-expanded={shown}
        aria-controls={id}
        onClick={() => {
          setByButton(true);
          show(!shown);
        }}
      >
        {action}
      </Button>
      {beneath ? createPortal(panel, beneath) : panel}
    </>
  );
}
