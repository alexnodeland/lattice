/**
 * Logs' window and filters, and Health's window and step, as the address keeps them (portalr
 * ADR-0031): the logs of the last hour, six or a day, a thread's or a run's, and the charts of the
 * last hour, day or week.
 */

import type { TimeSpan } from "@portalr/client";
import { windowOf } from "./traces";

/** The windows Logs offers, in hours, the first its default: a day at most, as portalr takes. */
export const LOG_RANGES = [
  { hours: 1, label: "The last hour" },
  { hours: 6, label: "The last 6 hours" },
  { hours: 24, label: "The last 24 hours" },
] as const;

/** The windows Health offers, in hours, the first its default. */
export const HEALTH_RANGES = [
  { hours: 1, label: "The last hour" },
  { hours: 24, label: "The last 24 hours" },
  { hours: 168, label: "The last 7 days" },
] as const;

export type LogHours = (typeof LOG_RANGES)[number]["hours"];
export type HealthHours = (typeof HEALTH_RANGES)[number]["hours"];

/** What Logs' address keeps: both windows, and a thread's or a run's id. */
export type Shown = {
  /** Always given by `shownOf`; optional for a link, which may leave it out. */
  readonly hours?: LogHours;
  readonly health?: HealthHours;
  readonly thread?: string | undefined;
  readonly run?: string | undefined;
};

const ID = /^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,127}$/;

/** An id from the address, trimmed: text, as the router reads `?run=42` as a number; or none. */
function idOf(value: unknown): string | undefined {
  const read = typeof value === "string" || typeof value === "number" ? String(value).trim() : "";
  return ID.test(read) ? read : undefined;
}

/**
 * The address's windows and filters: a window that isn't offered is its default, and an id that
 * isn't one is none, so the router keeps nothing portalr would refuse.
 */
export function shownOf(search: Record<string, unknown>): Required<Shown> {
  const hours = LOG_RANGES.find((one) => String(one.hours) === String(search.hours))?.hours;
  const health = HEALTH_RANGES.find((one) => String(one.hours) === String(search.health))?.hours;
  return {
    hours: hours ?? LOG_RANGES[0].hours,
    health: health ?? HEALTH_RANGES[0].hours,
    thread: idOf(search.thread),
    run: idOf(search.run),
  };
}

/** The logs' window: the hours up to the next whole minute, a day at most. */
export const logWindow = (hours: LogHours, now: Date): TimeSpan => windowOf(hours, now);

/** The steps a chart is drawn at, in seconds: a whole number of the units people read. */
const STEPS = [15, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 14_400] as const;

/** About this many points to a chart. */
const POINTS = 96;

/** The step for a window: the least that keeps it to about `POINTS` points. */
export const stepFor = (hours: number): number =>
  STEPS.find((step) => step >= (hours * 3600) / POINTS) ?? STEPS[STEPS.length - 1] ?? 14_400;

/** The health charts' window, at its step. */
export function healthWindow(hours: HealthHours, now: Date): TimeSpan {
  return { ...windowOf(hours, now), step: stepFor(hours) };
}

/** A step in words: `15 minutes`, `2 hours`. */
export function stepSaid(step: number): string {
  if (step < 60) {
    return `${step} seconds`;
  }
  const minutes = step / 60;
  if (minutes < 60) {
    return `${minutes} ${minutes === 1 ? "minute" : "minutes"}`;
  }
  const hours = minutes / 60;
  return `${hours} ${hours === 1 ? "hour" : "hours"}`;
}

/**
 * A point's time as an axis reads it, in UTC: the time of day, or the day too. UTC is never
 * repeated or skipped, as a zone's clock is where it changes, so no two points share a label.
 */
export function pointAt(seconds: number, hours: HealthHours): string {
  const iso = new Date(seconds * 1000).toISOString();
  return hours > 24 ? `${iso.slice(5, 10)} ${iso.slice(11, 16)}` : iso.slice(11, 16);
}

/**
 * A chart's points on the grid of its window, a step apart from its start: a step without a point
 * is `null`, which a line breaks at and a bar leaves empty, so a gap is shown as one.
 */
export function onGrid(
  window: TimeSpan,
  points: readonly { time: number; value: number }[],
): { time: number; value: number | null }[] {
  const step = window.step ?? 0;
  const found = new Map(points.map((point) => [Math.round(point.time), point.value]));
  const first = Math.round(Date.parse(window.start) / 1000);
  const last = Math.round(Date.parse(window.end) / 1000);
  const grid: { time: number; value: number | null }[] = [];
  for (let time = first; step > 0 && time <= last; time += step) {
    grid.push({ time, value: found.get(time) ?? null });
  }
  return grid;
}
