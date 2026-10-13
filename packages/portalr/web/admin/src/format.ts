/** How admin's screens write numbers: a count grouped, as a figure, in one place for every screen. */

/** Numbers grouped as people read them: 1,000. */
export const numbers = new Intl.NumberFormat("en-US");

/** A count, as a figure: grouped, and with a `+` where it reached what a read returns. */
export const figure = (count: number, limit?: number) =>
  limit !== undefined && count >= limit ? `${numbers.format(limit)}+` : numbers.format(count);
