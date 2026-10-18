/**
 * A moment as people read it: the time in their own zone, and how long ago it was on hover, as
 * admin's audit log shows it (portalr ADR-0021); and whether text is a moment or a day at all, as
 * artifactr.ui's checks read one.
 */

/**
 * A moment as RFC 3339 writes it, with its seconds and its offset, each part within its range, as
 * the package's check has it.
 */
const RFC_3339 =
  /^\d{4}-\d{2}-\d{2}[Tt]([01]\d|2[0-3]):[0-5]\d:[0-5]\d(\.\d+)?([Zz]|[+-]([01]\d|2[0-3]):[0-5]\d)$/u;

/** A day as the date input gives it, and the server takes it. */
const DAY = /^\d{4}-\d{2}-\d{2}$/u;

/** Whether a day is one the calendar has, from year 1: 2026-02-30 is not, nor 0000-01-01. */
export const realDay = (text: string) =>
  DAY.test(text) &&
  !text.startsWith("0000") &&
  new Date(`${text}T00:00:00Z`).toISOString().startsWith(text);

/** Whether a moment is one RFC 3339 writes, on a day the calendar has, from year 1. */
export const realMoment = (text: string) =>
  RFC_3339.test(text) &&
  realDay(text.slice(0, 10)) &&
  !Number.isNaN(Date.parse(text.toUpperCase()));

const UNITS: readonly [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 31_536_000],
  ["month", 2_592_000],
  ["week", 604_800],
  ["day", 86_400],
  ["hour", 3_600],
  ["minute", 60],
  ["second", 1],
];

const relative = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });

/** How long before or after `now` a moment is, in its largest whole unit: "3 hours ago". */
export function ago(at: Date, now: Date): string {
  const seconds = (at.getTime() - now.getTime()) / 1000;
  const [unit, size] = UNITS.find(([, size]) => Math.abs(seconds) >= size) ?? ["second", 1];
  return relative.format(Math.round(seconds / size), unit);
}

/** A `<time>`: the moment in the reader's zone, and, on hover, how long ago it was. */
export function Moment({ at, now = new Date() }: { at: string; now?: Date }) {
  const when = new Date(at);
  return (
    <time dateTime={at} title={ago(when, now)}>
      {when.toLocaleString()}
    </time>
  );
}
