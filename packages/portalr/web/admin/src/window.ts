/**
 * The windows Feedback and Usage read: whole days in UTC, ending with today's, the same all day,
 * as portalr sums each by day (portalr ADR-0027, ADR-0028).
 */

import type { TimeSpan } from "@portalr/client";

/** The windows offered, in days, the first the default. */
export const WINDOWS = [7, 30, 90] as const;
export type Days = (typeof WINDOWS)[number];

/** The address's window: one offered, or the default. */
export const daysOf = (days: unknown): Days =>
  WINDOWS.find((one) => String(one) === String(days)) ?? WINDOWS[0];

const DAY = 86_400_000;

/**
 * A window of whole days in UTC, ending with today's: the same all day, so a read of it is one
 * query, whenever in the day it is made.
 */
export function windowOf(days: Days, now: Date): TimeSpan {
  const today = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  return {
    start: new Date(today - (days - 1) * DAY).toISOString(),
    end: new Date(today + DAY).toISOString(),
  };
}
