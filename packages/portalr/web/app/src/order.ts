/** Orders for the workspace's lists. */

/** A moment as milliseconds; one that can't be read is the oldest, so the order stays total. */
const moment = (at: string) => {
  const ms = Date.parse(at);
  return Number.isNaN(ms) ? Number.NEGATIVE_INFINITY : ms;
};

/**
 * The most recently made or changed first, compared as moments, not as text, since two offsets
 * write one moment differently; ties, and moments that can't be read, by id.
 */
export function newestFirst(
  a: { readonly id: string; readonly changedAt: string },
  b: { readonly id: string; readonly changedAt: string },
): number {
  const [left, right] = [moment(a.changedAt), moment(b.changedAt)];
  return left === right ? a.id.localeCompare(b.id) : right > left ? 1 : -1;
}
