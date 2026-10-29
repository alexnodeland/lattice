/**
 * The tray above the composer (portalr ADR-0092): what waits for the person, a question or a
 * proposal to review, docked with the composer so it is never scrolled away, as one thing and not
 * as cards in the thread. One waiting is shown whole; several are one line, counted, that opens to
 * all of them. It scrolls inside itself past a share of the window's height, so the composer
 * keeps its room.
 */

import { Button as BaseButton } from "@base-ui/react/button";
import { Fragment, type ReactNode, useEffect, useId, useRef, useState } from "react";
import { cn } from "./cn";
import { Icon } from "./icon";
import { glyphs } from "./icons";
import { RING } from "./states";
import { StatusBadge } from "./status-badge";

export interface Waiting {
  /** Its own, among the tray's. */
  readonly key: string;
  /** What it is, in a few words, for the line that counts several. */
  readonly label: string;
  readonly children: ReactNode;
}

export function Tray({ waiting }: { waiting: readonly Waiting[] }) {
  const body = useRef<HTMLDivElement>(null);
  const list = useId();
  const [opened, setOpened] = useState(false);
  const several = waiting.length > 1;
  const open = !several || opened;
  // A link to one of them, as a file's "changes are waiting", opens the tray it is closed in.
  useEffect(() => {
    const reveal = () => {
      const target = document.getElementById(location.hash.slice(1));
      if (target !== null && body.current?.contains(target)) {
        setOpened(true);
        requestAnimationFrame(() => target.focus());
      }
    };
    addEventListener("hashchange", reveal);
    return () => removeEventListener("hashchange", reveal);
  }, []);
  if (waiting.length === 0) {
    return null;
  }
  return (
    <section aria-label="Waiting for you" className="flex min-w-0 flex-col gap-2">
      {several && (
        <BaseButton
          aria-expanded={open}
          aria-controls={list}
          onClick={() => setOpened(!opened)}
          className={cn(
            "flex min-h-11 w-full min-w-0 cursor-pointer items-center gap-2 rounded-(--card-radius) border border-line bg-surface px-3 text-start text-sm",
            RING,
          )}
        >
          <StatusBadge tone="waiting" className="shrink-0">
            {waiting.length} waiting for you
          </StatusBadge>
          <span className="min-w-0 flex-1 truncate text-muted text-xs">
            {waiting.map(({ label }) => label).join(" · ")}
          </span>
          <Icon
            icon={glyphs.chevronRight}
            className={cn(
              "size-3.5 shrink-0 text-muted transition-transform duration-(--disclosure-duration) motion-reduce:transition-none",
              open && "rotate-90",
            )}
          />
        </BaseButton>
      )}
      <div ref={body} id={list} hidden={!open} className="as-tray-body flex min-w-0 flex-col gap-2">
        {waiting.map(({ key, children }) => (
          <Fragment key={key}>{children}</Fragment>
        ))}
      </div>
    </section>
  );
}
