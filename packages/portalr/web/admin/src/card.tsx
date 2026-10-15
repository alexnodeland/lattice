/**
 * How each of Home's cards reads: on its own, so one that is out or failed holds no other. While
 * it reads, it says so and is busy; a read refused because the reader may not hides the card;
 * any other failure says so on the card, with a shape and a word.
 */

import { Refused } from "@portalr/client";
import { StatCard, StatusBadge } from "@portalr/ui";
import { CatchBoundary } from "@tanstack/react-router";
import { type ReactNode, Suspense } from "react";
import type { Said } from "./home";

/** A card's words, figure and badge, as `home.ts` derived them. */
export function SaidCard({ title, said }: { title: string; said: Said }) {
  return (
    <StatCard
      title={title}
      figure={said.figure}
      badge={said.badge && <StatusBadge tone={said.badge.tone}>{said.badge.word}</StatusBadge>}
    >
      {said.note ? <span title={said.note}>{said.line}</span> : said.line}
    </StatCard>
  );
}

/** One card's read, guarded: `children` reads with suspense. */
export function Guarded({ title, children }: { title: string; children: ReactNode }) {
  return (
    <CatchBoundary
      getResetKey={() => title}
      errorComponent={({ error }) =>
        error instanceof Refused && error.status === 403 ? null : (
          <SaidCard
            title={title}
            said={{
              figure: null,
              line: "This couldn't be read.",
              badge: { tone: "failed", word: "Failed" },
            }}
          />
        )
      }
    >
      <Suspense
        fallback={
          <StatCard title={title} figure={null} busy>
            Reading…
          </StatCard>
        }
      >
        {children}
      </Suspense>
    </CatchBoundary>
  );
}
