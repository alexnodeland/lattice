/**
 * Adoption's window, as its address keeps it, and what its tables and charts make of portalr's
 * adoption read: people active each day, each integration's people, the funnel from a page to a
 * thread to a message, and weekly retention (portalr ADR-0071).
 */

import type { PortalrApi } from "@portalr/client";
import { type Days, daysOf } from "./window";

type Adoption = PortalrApi.components["schemas"]["Adoption"];

/** What Adoption's address keeps: the window, in days. */
export type Shown = {
  /** Always given by `shownOf`; optional for a link, which may leave it out. */
  readonly days?: Days;
};

/** The address's window: one Adoption offers, or its default. */
export const shownOf = (search: Record<string, unknown>): Required<Shown> => ({
  days: daysOf(search.days),
});

/** A part of a whole, as a share people read: 2 of 3 as "67%"; none of none as "–". */
export const shareOf = (part: number, whole: number) =>
  whole > 0 ? `${Math.round((part / whole) * 100)}%` : "–";

/** One step of the funnel: what people did, how many did, and their share of the first step. */
export type Step = { readonly key: string; readonly name: string; readonly people: number };

/** The funnel's steps, in order: each counts the people who did it after the ones before. */
export const stepsOf = (funnel: NonNullable<Adoption["funnel"]>): Step[] => [
  { key: "page", name: "Viewed a page", people: funnel.page },
  { key: "thread", name: "Then opened a thread", people: funnel.thread },
  { key: "message", name: "Then sent a message", people: funnel.message },
];

/** One week of retention: which week of the window, and how many of its first week's people. */
export type Week = { readonly week: number; readonly people: number };

/** Each week of the window, the first first, with how many of the first week's people were active. */
export const weeksOf = (retention: readonly number[]): Week[] =>
  retention.map((people, week) => ({ week, people }));

/** What a week of the window is called: the first as "Week 1". */
export const weekSaid = (week: number) => `Week ${week + 1}`;
