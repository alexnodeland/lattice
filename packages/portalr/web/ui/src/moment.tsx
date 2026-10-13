/**
 * A moment as people read it: the time in their own zone, and how long ago it was on hover, as
 * admin's audit log shows it (portalr ADR-0021).
 */

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
