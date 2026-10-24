/**
 * What Home's cards say of what their reads answered: each from one read, with its own state, so
 * a tool that is down, or isn't configured, fails its own card alone (lattice RFC-0002). Each
 * card's words are derived here, from the read's own type, so each state is tested apart from
 * the page.
 */

import type { GrantrApi, PortalrApi, TimeSpan } from "@portalr/client";
import type { Tone } from "@portalr/ui";
import { dollars, figure, numbers } from "./format";

type Schemas = PortalrApi.components["schemas"];

/** A tool that didn't answer, or that the application runs without: every reading's other two. */
type Unread = Schemas["Unavailable"] | Schemas["Unconfigured"];

export type SpendReading = Schemas["Ok_Union_Spend__NoneType__"] | Unread;
export type ScoresReading = Schemas["Ok_Scores_"] | Unread;
export type PointsReading = Schemas["Ok_list_Point__"] | Unread;
export type TenantSpendReading = Schemas["Ok_list_TenantSpend__"] | Unread;

/** A state a card shows beside its words, as a shape and a word (portalr ADR-0021). */
interface Badge {
  readonly tone: Tone;
  readonly word: string;
}

/** What a card shows: its figure, or none, the line under it, and a badge for its state. */
export interface Said {
  readonly figure: string | null;
  readonly line: string;
  /** A fuller word on what the line counts, shown small beneath it. */
  readonly note?: string;
  readonly badge?: Badge;
}

/** A count of something, with its noun as one or many. */
export const counted = (count: number, one: string, many = `${one}s`) =>
  `${numbers.format(count)} ${count === 1 ? one : many}`;

/** A card's words for a tool that didn't answer, or that the application runs without. */
export function unread(tool: string, reading: Unread): Said {
  return reading.status === "unavailable"
    ? {
        figure: null,
        line: `${tool} isn't answering.`,
        badge: { tone: "failed", word: "Unavailable" },
      }
    : {
        figure: null,
        line: `${tool} isn't configured.`,
        badge: { tone: "stopped", word: "Not configured" },
      };
}

/**
 * The days up to this second, and, for a series, the step between its points: read once as a
 * card opens, so its key holds while it is open.
 */
export function spanOf(now: Date, days: number, step?: number): TimeSpan {
  const end = new Date(now);
  end.setUTCMilliseconds(0);
  const start = new Date(end.getTime() - days * 86_400_000);
  return {
    start: start.toISOString(),
    end: end.toISOString(),
    ...(step !== undefined && { step }),
  };
}

export function membersSaid(members: readonly GrantrApi.components["schemas"]["Member"][]): Said {
  const people = members.filter((member) => member.kind === "user").length;
  return {
    figure: figure(members.length),
    line: `${counted(people, "person", "people")} and ${counted(members.length - people, "service principal")}`,
  };
}

export function workspacesSaid(workspaces: readonly string[]): Said {
  return { figure: figure(workspaces.length), line: "with a log you can open in artifactr" };
}

/**
 * People's feedback over the window: the scores no evaluator gave, and, of the thumbs among them,
 * how many were up. Langfuse sends a yes-or-no as 1 or 0. A read that stopped at one of its bounds
 * shows its figure as at least that, and says it is partial.
 */
export function feedbackSaid(reading: ScoresReading): Said {
  if (reading.status !== "ok") {
    return unread("Langfuse", reading);
  }
  const { scores, complete } = reading.data;
  const given = scores.filter((score) => !score.evaluator);
  const thumbs = given.filter(
    (score) => score.feedback_type === "thumbs" && score.data_type === "BOOLEAN",
  );
  const up = thumbs.filter((score) => score.value === true || score.value === 1).length;
  const scored = "pieces of feedback in the last week";
  return {
    figure: figure(given.length, !complete),
    line: thumbs.length
      ? `${scored}; ${numbers.format(up)} of ${numbers.format(thumbs.length)} thumbs up`
      : scored,
    ...(!complete && { badge: { tone: "stopped", word: "Partial" } }),
  };
}

/**
 * Failed turns over the window: the last point, which counts the failures in the step before it.
 * They are artifactr's agent turns, not reflexr's rule runs.
 */
export function failuresSaid(reading: PointsReading): Said {
  if (reading.status !== "ok") {
    return unread("Prometheus", reading);
  }
  const last = reading.data.at(-1)?.value ?? 0;
  return {
    figure: figure(Math.round(last)),
    line: "agent turns in the last day",
    note: "Not rules' runs: a rule's run that fails isn't counted here.",
  };
}

/** How far through its budget a tenant's spend is: under, near (80% or more), over it, or none. */
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

/** LiteLLM's budget durations, such as `30d` or `1h`, in words. */
export function duration(period: string): string {
  const units: Record<string, readonly [string, string]> = {
    s: ["second", "seconds"],
    m: ["minute", "minutes"],
    h: ["hour", "hours"],
    d: ["day", "days"],
    mo: ["month", "months"],
  };
  const matched = /^(\d+)(mo|[smhd])$/.exec(period);
  const unit = matched ? units[matched[2] ?? ""] : undefined;
  if (!(matched && unit)) {
    return period;
  }
  const count = Number(matched[1]);
  return count === 1 ? `${unit[0]}` : `${numbers.format(count)} ${unit[1]}`;
}

export function spendSaid(reading: SpendReading): Said {
  if (reading.status !== "ok") {
    return unread("LiteLLM", reading);
  }
  const spend = reading.data;
  if (!spend) {
    return { figure: null, line: "The tenant has no team in LiteLLM yet." };
  }
  const state = budget(spend);
  if (state === "none") {
    return { figure: dollars(spend.spend), line: "No budget is set." };
  }
  const period = spend.budget_duration ? `, every ${duration(spend.budget_duration)}` : "";
  return {
    figure: dollars(spend.spend),
    line: `of ${dollars(spend.max_budget ?? 0)}${period}`,
    ...(state === "near" && { badge: { tone: "near", word: "Near budget" } as const }),
    ...(state === "over" && { badge: { tone: "over", word: "Over budget" } as const }),
  };
}

export function deploymentSpendSaid(reading: TenantSpendReading): Said {
  if (reading.status !== "ok") {
    return unread("LiteLLM", reading);
  }
  const total = reading.data.reduce((sum, each) => sum + each.spend, 0);
  return { figure: dollars(total), line: "across every tenant's LiteLLM team" };
}
