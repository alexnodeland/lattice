/**
 * Traces' window and filters, as its address keeps them: the last hour, day or week, and a thread's
 * or a run's, which portalr searches Tempo for (portalr ADR-0030).
 */

import type { TimeSpan } from "@portalr/client";

/** The windows Traces offers, in hours, the first its default. */
export const RANGES = [
  { hours: 1, label: "1 hour" },
  { hours: 24, label: "24 hours" },
  { hours: 168, label: "7 days" },
] as const;

type Hours = (typeof RANGES)[number]["hours"];

/** What an id may be, as portalr takes one: the pattern its reads check ids by. */
export const ID_PATTERN = "[A-Za-z0-9][A-Za-z0-9_.:@\\-]{0,127}";
const ID = new RegExp(`^${ID_PATTERN}$`);

/** What Traces' address keeps: the window, in hours, a thread's or a run's id, and an analytics session's. */
export type Shown = {
  /** Always given by `shownOf`; optional for a link, which may leave it out. */
  readonly hours?: Hours;
  readonly thread?: string | undefined;
  readonly run?: string | undefined;
  /** An analytics session, whose requests' traces are shown (portalr ADR-0073). */
  readonly analytics?: string | undefined;
};

/** An analytics session's id, as portalr's relay makes it: when it began, and 16 hex digits. */
const ANALYTICS_SESSION = /^\d{1,12}-[0-9a-f]{16}$/;

/** The span attribute portalr sets on a request's server span: its analytics session. */
export const ANALYTICS_ATTRIBUTE = "portalr.analytics.session";

/** A trace's analytics session, from the first of its spans that names one; or none. */
export function analyticsSessionOf(
  spans: readonly { readonly attributes: Readonly<Record<string, unknown>> }[],
): string | undefined {
  for (const span of spans) {
    const session = span.attributes[ANALYTICS_ATTRIBUTE];
    if (typeof session === "string" && ANALYTICS_SESSION.test(session)) {
      return session;
    }
  }
  return undefined;
}

/** Whether text is an id portalr takes, such as a trace's: what its reads check ids by. */
export const isId = (text: string) => ID.test(text);

/** An id from the address, trimmed: text, as the router reads `?run=42` as a number; or none. */
function idOf(value: unknown): string | undefined {
  const read = typeof value === "string" || typeof value === "number" ? String(value).trim() : "";
  return ID.test(read) ? read : undefined;
}

/**
 * The address's window and filters: a window Traces doesn't offer is its default, and an id that
 * isn't one is none, so the router keeps nothing portalr would refuse.
 */
export function shownOf(search: Record<string, unknown>): Required<Shown> {
  const hours = RANGES.find((one) => String(one.hours) === String(search.hours))?.hours;
  const analytics = typeof search.analytics === "string" ? search.analytics : "";
  return {
    hours: hours ?? RANGES[0].hours,
    thread: idOf(search.thread),
    run: idOf(search.run),
    analytics: ANALYTICS_SESSION.test(analytics) ? analytics : undefined,
  };
}

const MINUTE = 60_000;

/** The window ending at the next whole minute, so a read of it holds a minute, whenever in it. */
export function windowOf(hours: number, now: Date): TimeSpan {
  const end = Math.ceil(now.getTime() / MINUTE) * MINUTE;
  return {
    start: new Date(end - hours * 3_600_000).toISOString(),
    end: new Date(end).toISOString(),
  };
}

/** When a trace began, from Tempo's nanoseconds, as the ISO moment a screen reads. */
export const startedAt = (startNs: number) => new Date(startNs / 1_000_000).toISOString();
