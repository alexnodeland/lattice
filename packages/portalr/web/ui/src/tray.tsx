/**
 * The tray above the composer (portalr ADR-0092): what waits for the person, a question or a
 * proposal to review, docked with the composer so it is never scrolled away, as one thing and not
 * as cards in the thread. One waiting is shown whole; several are one line, counted, that opens to
 * all of them, and stays open if it was open as another came. It scrolls inside itself past a
 * share of the window's height (never less than a few lines), with a fade at an edge there is more
 * past, so the composer keeps its room. Whatever reaches into it, a link, a hash, "Go to the
 * question", opens it first.
 */

import type { Artifactr, ArtifactrV1 } from "@portalr/client";
import { type ReactNode, useEffect, useState } from "react";
import { proposalTitle } from "./chat";
import { Disclosure } from "./disclosure";
import { readQuestions } from "./questions";
import { StatusBadge } from "./status-badge";

/** What a request asks, in a few words, for a line that counts them: its first question, or "A form". */
export function askedOf(request: ArtifactrV1.DeferredRequest): string {
  return readQuestions(request.args)?.[0]?.question ?? "A form";
}

/**
 * A proposal that was decided, as one line of the thread (portalr ADR-0092): what it was, and
 * whether it was accepted or rejected. Its card is for the one that waits.
 */
export function ProposalLine({ proposal }: { proposal: Artifactr.Proposal }) {
  const what = proposalTitle(proposal);
  const accepted = proposal.status === "accept";
  return (
    <li className="flex items-center gap-2 text-xs">
      <StatusBadge tone={accepted ? "done" : "stopped"} className="shrink-0">
        {accepted ? "Accepted" : "Rejected"}
      </StatusBadge>
      <span className="min-w-0 truncate text-muted">{what}</span>
    </li>
  );
}

export interface Waiting {
  /** What it is, in a few words, for the line that counts several. */
  readonly label: string;
  /** Under a `key` of its own. */
  readonly children: ReactNode;
}

/** The page's tray, which opens as asked: there is one, and it says how while it is there. */
let openTray: ((id: string) => void) | undefined;

/** The focus to the element `id`, or to the first named part of a request's card, "The agent asks". */
function focusAt(id: string) {
  const target = document.getElementById(id);
  const named = id.startsWith("request-")
    ? target?.querySelector<HTMLElement>("[aria-label], [aria-labelledby]")
    : null;
  const at = named ?? target;
  if (at) {
    at.tabIndex = -1;
    at.focus();
  }
}

/** To the element `id`, if a tray holds it: the tray opens at it, with the focus. */
function reach(id: string): boolean {
  const held = document.getElementById(id)?.closest("[data-tray]") != null;
  if (held) {
    openTray?.(id);
  }
  return held;
}

/** To the element `id`, with the focus: in the tray, which opens at it, if it is shut. */
export function reachWaiting(id: string) {
  reach(id) || focusAt(id);
}

export function Tray({
  waiting,
  reach: arrived,
}: {
  waiting: readonly Waiting[];
  /** A request that has just arrived, which the tray opens at, as a reach does. */
  reach?: string | undefined;
}) {
  // Several are closed at first; one is shown whole, and what is open stays so as another comes;
  // none shuts it for the next several.
  const [opened, setOpened] = useState(false);
  useEffect(() => {
    if (waiting.length < 2) {
      setOpened(waiting.length === 1);
    }
  }, [waiting.length]);
  const several = waiting.length > 1;
  const present = waiting.length > 0;
  // The focus goes where it was asked once the tray has been opened, not before.
  const [reached, setReached] = useState<{ id: string }>();
  useEffect(() => {
    if (reached) {
      focusAt(reached.id);
    }
  }, [reached]);
  useEffect(() => {
    openTray = (id) => {
      setOpened(true);
      setReached({ id });
    };
    // A link to what is already the hash fires no change: its click does.
    const click = (event: MouseEvent) => {
      const link = (event.target as Element).closest<HTMLAnchorElement>("a[href^='#']");
      if (link) {
        reach(link.hash.slice(1));
      }
    };
    // Where the page was opened at one of them, or one has arrived, once it is in.
    reach(arrived ? `request-${arrived}` : location.hash.slice(1));
    document.addEventListener("click", click);
    return () => {
      openTray = undefined;
      document.removeEventListener("click", click);
    };
  }, [present, arrived]);
  const items = (
    <div data-tray="" className="as-tray-body flex min-w-0 flex-col gap-2">
      {waiting.map(({ children }) => children)}
    </div>
  );
  return (
    <>
      {/* There before anything is in it, so what arrives is announced. */}
      <span role="status" className="sr-only">
        {present && `${waiting.length} waiting for you`}
      </span>
      {present && (
        <section aria-label="Waiting for you" className="min-w-0">
          {/* The same tree as one comes and another, so what the reader is at is neither remounted nor
              hidden: the line that counts them is no part of it while there is one. */}
          <Disclosure
            look="block"
            open={several ? opened : true}
            onOpenChange={setOpened}
            triggerClassName={
              several
                ? "mb-2 min-h-11 items-center rounded-(--card-radius) border border-line bg-surface px-3 text-sm"
                : "!hidden"
            }
            panelClassName="data-open:pt-0"
            summary={
              several && (
                <>
                  <StatusBadge tone="waiting" className="shrink-0">
                    {waiting.length} waiting for you
                  </StatusBadge>
                  <span className="min-w-0 flex-1 truncate text-muted text-xs">
                    {waiting.map(({ label }) => label).join(" · ")}
                  </span>
                </>
              )
            }
          >
            {items}
          </Disclosure>
        </section>
      )}
    </>
  );
}
