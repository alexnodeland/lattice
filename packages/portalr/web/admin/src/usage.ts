/**
 * Usage's window, as its address keeps it, and what its tracker and charts make of portalr's
 * usage read: each day's spend against its share of the team's budget, and each workspace's
 * part (portalr ADR-0028).
 */

import type { PortalrApi } from "@portalr/client";
import type { Block, Level, Part } from "@portalr/ui";
import { dollars } from "./format";
import { type Days, daysOf } from "./window";

type Usage = PortalrApi.components["schemas"]["Usage"];

/** What Usage's address keeps: the window, in days. */
export type Shown = {
  /** Always given by `shownOf`; optional for a link, which may leave it out. */
  readonly days?: Days;
};

/** The address's window: one Usage offers, or its default. */
export const shownOf = (search: Record<string, unknown>): Required<Shown> => ({
  days: daysOf(search.days),
});

/** The most workspaces one read splits the spend by: portalr's `MOST_WORKSPACES`, as it allows. */
export const MOST_WORKSPACES = 50;

/** The workspaces a read asks after: the tenant's, in order, fifty at most. */
export const askedOf = (workspaces: readonly string[]) =>
  [...workspaces].sort().slice(0, MOST_WORKSPACES);

/** How far through its share of the budget a day's spend is, the least first. */
export const LEVELS: readonly Level[] = [
  { key: "none", name: "Nothing spent" },
  { key: "under", name: "Under its share" },
  { key: "near", name: "Near its share (80% or more)" },
  { key: "over", name: "Over its share" },
];

/** A day's level, by its spend and its share of the budget: one of `LEVELS`. */
export function levelOf(spend: number, share: number): number {
  if (spend <= 0) {
    return 0;
  }
  if (spend > share) {
    return 3;
  }
  return spend >= share * 0.8 ? 2 : 1;
}

/** A day as an axis reads it, in UTC: `10-13`. The tables and titles keep the whole date. */
export const short = (day: string) => day.slice(5);

/**
 * Each day the read reached as a block of the tracker, against its share of the budget. A day a
 * partial read never reached isn't in `usage.days`, so it is no block: unknown isn't nothing spent.
 */
export const blocksOf = (usage: Usage, share: number): Block[] =>
  usage.days.map((day) => ({
    key: day.day,
    name: day.day,
    level: levelOf(day.spend, share),
    figure: dollars(day.spend),
  }));

/** Less than a cent: what is left of the spend once the workspaces' is taken from it. */
const CENT = 0.005;

/**
 * Each workspace's part of the window's spend, and, where both reads ran to their end, the part
 * no workspace's tag holds: spend before the libraries tagged it, or on a workspace the read
 * didn't ask after. A partial read's two totals cover different days, so their difference is no
 * part of anything.
 */
export function partsOf(usage: Usage): Part[] {
  const spent = usage.days.reduce((sum, day) => sum + day.spend, 0);
  const parts = usage.workspaces.map((place) => ({
    key: place.workspace,
    name: place.workspace,
    value: place.spend,
  }));
  const rest = spent - parts.reduce((sum, part) => sum + part.value, 0);
  return usage.complete && rest >= CENT
    ? [...parts, { key: "~untagged", name: "No workspace", value: rest }]
    : parts;
}
