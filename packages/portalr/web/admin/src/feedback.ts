/**
 * Feedback and evaluations as admin's charts and tables read them: a tenant's scores from
 * Langfuse, bucketed by day in the browser. People's feedback is the scores no evaluator gave,
 * thumbs up or down; an evaluation is an evaluator's score, numeric or yes-or-no, averaged per day
 * (portalr ADR-0027).
 */

import type { PortalrApi, TimeSpan } from "@portalr/client";

type Score = PortalrApi.components["schemas"]["Score"];

/** The windows Feedback offers, in days, the first its default. */
export const WINDOWS = [7, 30, 90] as const;
export type Days = (typeof WINDOWS)[number];

/** The most series one chart draws; the rest are in the table beneath it (ADR-0021's inks). */
export const SERIES = 3;

const DAY = 86_400_000;

/** A window of whole days in UTC, ending with today's, as far as `now`. */
export function windowOf(days: Days, now: Date): TimeSpan {
  const today = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  return { start: new Date(today - (days - 1) * DAY).toISOString(), end: now.toISOString() };
}

/** A moment's day, in UTC: `2026-10-13`. */
export const dayOf = (at: string) => at.slice(0, 10);

/** Each day of a window, oldest first. */
export function daysIn(window: TimeSpan): string[] {
  const days: string[] = [];
  for (let at = Date.parse(window.start); at <= Date.parse(window.end); at += DAY) {
    days.push(new Date(at).toISOString().slice(0, 10));
  }
  return days;
}

/** A person's feedback: a score no evaluator gave. */
export const isPeoples = (score: Score) => !score.evaluator;

/** Thumbs up and down on one day. */
export interface Thumbs {
  readonly day: string;
  readonly up: number;
  readonly down: number;
}

/** People's thumbs, per day of the window: a thumb is a yes-or-no score no evaluator gave. */
export function thumbsByDay(scores: readonly Score[], days: readonly string[]): Thumbs[] {
  const counted = new Map(days.map((day) => [day, { day, up: 0, down: 0 }]));
  for (const score of scores) {
    const day = counted.get(dayOf(score.timestamp));
    if (day && isPeoples(score) && typeof score.value === "boolean") {
      if (score.value) {
        day.up += 1;
      } else {
        day.down += 1;
      }
    }
  }
  return [...counted.values()];
}

/** An evaluation's series: its evaluator and score's name, and its mean on each day, if any. */
export interface Trend {
  readonly name: string;
  readonly count: number;
  readonly points: readonly { readonly day: string; readonly mean: number | null }[];
}

/** A score as a number to average: numeric as it is, yes as 1 and no as 0; else none. */
function numeric(score: Score): number | null {
  if (typeof score.value === "boolean") {
    return score.value ? 1 : 0;
  }
  return score.data_type === "NUMERIC" && typeof score.value === "number" ? score.value : null;
}

/** Each evaluation's mean per day, the most scored first: an evaluator's numeric or yes-or-no. */
export function trends(scores: readonly Score[], days: readonly string[]): Trend[] {
  const series = new Map<string, Map<string, number[]>>();
  for (const score of scores) {
    const value = numeric(score);
    if (score.evaluator && value !== null) {
      const name = `${score.evaluator} · ${score.name}`;
      const byDay = series.get(name) ?? new Map<string, number[]>();
      byDay.set(dayOf(score.timestamp), [...(byDay.get(dayOf(score.timestamp)) ?? []), value]);
      series.set(name, byDay);
    }
  }
  return [...series.entries()]
    .map(([name, byDay]) => ({
      name,
      count: [...byDay.values()].reduce((sum, values) => sum + values.length, 0),
      points: days.map((day) => {
        const values = byDay.get(day);
        return { day, mean: values ? values.reduce((a, b) => a + b, 0) / values.length : null };
      }),
    }))
    .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
}

/** One workspace's share: its people's thumbs, and how many evaluations it had. */
export interface Place {
  readonly workspace: string | null;
  readonly up: number;
  readonly down: number;
  readonly evaluated: number;
}

/** Each workspace's thumbs and evaluations, the busiest first; null for traces in none. */
export function byWorkspace(scores: readonly Score[]): Place[] {
  const places = new Map<string | null, { up: number; down: number; evaluated: number }>();
  for (const score of scores) {
    const place = places.get(score.workspace ?? null) ?? { up: 0, down: 0, evaluated: 0 };
    if (score.evaluator) {
      place.evaluated += 1;
    } else if (score.value === true) {
      place.up += 1;
    } else if (score.value === false) {
      place.down += 1;
    }
    places.set(score.workspace ?? null, place);
  }
  return [...places.entries()]
    .map(([workspace, place]) => ({ workspace, ...place }))
    .sort(
      (a, b) =>
        b.up + b.down + b.evaluated - (a.up + a.down + a.evaluated) ||
        (a.workspace ?? "").localeCompare(b.workspace ?? ""),
    );
}

/** People's comments, newest first: what they said beside a thumb. */
export const comments = (scores: readonly Score[]) =>
  scores
    .filter((score) => isPeoples(score) && score.comment)
    .sort((a, b) => b.timestamp.localeCompare(a.timestamp));
