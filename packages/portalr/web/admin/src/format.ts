/** How admin's screens write numbers, counts and money, in one place for every screen. */

/** Numbers grouped as people read them: 1,000. */
export const numbers = new Intl.NumberFormat("en-US");

/** A count, as a figure: grouped, and with a `+` where a read stopped short, so it may be more. */
export const figure = (count: number, short = false) =>
  `${numbers.format(count)}${short ? "+" : ""}`;

/** An amount of money, as LiteLLM counts spend: in US dollars. */
export const dollars = (amount: number) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(amount);
