/**
 * What Home's cards say of what their reads answered: each from one read, with its own state, so
 * a tool that is down, or isn't configured, fails its own card alone (lattice RFC-0002).
 */

import type { PortalrApi, Window } from "@portalr/client";

type Schemas = PortalrApi.components["schemas"];

/** A tool's answer: its data, that it is down, or that the application runs without it. */
export type Reading<T> =
  | { readonly status: "ok"; readonly data: T }
  | { readonly status: "unavailable"; readonly reason: string }
  | { readonly status: "unconfigured" };

/** What a card shows: its figure, or none, and the line under it. */
export interface Said {
  readonly figure: string | null;
  readonly line: string;
}

/** A card's words for a tool that didn't answer, or that the application runs without. */
export function unread(tool: string, reading: Reading<unknown>): Said | null {
  switch (reading.status) {
    case "ok":
      return null;
    case "unavailable":
      return { figure: null, line: `${tool} isn't answering: ${reading.reason}` };
    case "unconfigured":
      return { figure: null, line: `${tool} isn't configured.` };
    default:
      return reading satisfies never;
  }
}

/**
 * The days up to this minute, and, for a series, the step between its points: read once as a card
 * opens, so its key holds while it is open.
 */
export function windowOf(now: Date, days: number, step?: number): Window {
  const end = new Date(now);
  end.setUTCSeconds(0, 0);
  const start = new Date(end.getTime() - days * 86_400_000);
  return {
    start: start.toISOString(),
    end: end.toISOString(),
    ...(step !== undefined && { step }),
  };
}

/** About how many runs failed over a series of failure rates, each held for `step` seconds. */
export function failures(points: readonly Schemas["Point"][], step: number): number {
  return Math.round(points.reduce((total, point) => total + point.value * step, 0));
}

/** How far through its budget a tenant's spend is: under, near (80% or more) or over it. */
export type Budget = "under" | "near" | "over" | "none";

export function budget(spend: Schemas["Spend"]): Budget {
  const { max_budget: max } = spend;
  if (max === null || max === undefined || max <= 0) {
    return "none";
  }
  if (spend.spend > max) {
    return "over";
  }
  return spend.spend >= max * 0.8 ? "near" : "under";
}

/** An amount of money, as LiteLLM counts spend: in US dollars. */
export const dollars = (amount: number) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(amount);

/** A count of something, with its noun as one or many. */
export const counted = (count: number, one: string, many = `${one}s`) =>
  `${count} ${count === 1 ? one : many}`;
