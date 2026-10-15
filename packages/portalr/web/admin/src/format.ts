/** How admin's screens write numbers and sentences, in one place for every screen. */

/** Numbers grouped as people read them: 1,000. */
export const numbers = new Intl.NumberFormat("en-US");

/** A count, as a figure: grouped, and with a `+` where a read stopped short, so it may be more. */
export const figure = (count: number, short = false) =>
  `${numbers.format(count)}${short ? "+" : ""}`;

/** What a failure says, as a sentence of its own: its message's first letter a capital. */
export const failureSaid = (error: unknown) => {
  const said = error instanceof Error ? error.message : String(error);
  return said.charAt(0).toUpperCase() + said.slice(1);
};
