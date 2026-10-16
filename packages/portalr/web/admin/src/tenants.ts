/**
 * Tenants' rows and form (portalr ADR-0034): every tenant grantr has, with what LiteLLM says its
 * team spends, a page of them at a time, and what a new tenant's id and owner's email must be.
 */

import type { PortalrApi } from "@portalr/client";
import { dollars } from "./format";
import { durationSaid } from "./usage";

type Schemas = PortalrApi.components["schemas"];
type TenantSpend = Schemas["TenantSpend"];

/** How many tenants a page lists: the list pages on the client, for up to a few hundred. */
export const PAGE = 50;

/** A tenant, and its LiteLLM team's spend, if it has a team and LiteLLM answered. */
export interface Row {
  readonly tenant: string;
  readonly team: TenantSpend | null;
}

/** The tenants, by name, each with its team: `reading` is LiteLLM's one team list. */
export function rowsOf(
  tenants: readonly string[],
  reading: Schemas["Ok_list_TenantSpend__"] | Schemas["Unavailable"] | Schemas["Unconfigured"],
): Row[] {
  const teams = new Map(
    reading.status === "ok" ? reading.data.map((each) => [each.tenant, each]) : [],
  );
  return [...tenants]
    .sort((a, b) => a.localeCompare(b))
    .map((tenant) => ({ tenant, team: teams.get(tenant) ?? null }));
}

/** A tenant's spend, in dollars, or a dash where LiteLLM didn't say. */
export const spendSaid = (row: Row) => (row.team ? dollars(row.team.spend) : "–");

/**
 * A tenant's budget in words: what it is and how much of it is spent, or why there is none to say:
 * LiteLLM didn't answer, the tenant has no team, or its team has no budget.
 */
export function budgetSaid(row: Row, answered: boolean): string {
  if (!answered) {
    return "–";
  }
  if (row.team === null) {
    return "No budget";
  }
  const { max_budget: max, budget_duration: duration, spend } = row.team;
  if (!max) {
    return "No budget set";
  }
  const used = Math.round((spend / max) * 100);
  return `${dollars(max)} ${duration ? durationSaid(duration) : ""}, ${used}% spent`.replace(
    " ,",
    ",",
  );
}

/** A tenant id as grantr takes one: not empty, with no `~`. */
export const isTenantId = (text: string) => text.trim() !== "" && !text.includes("~");

/** An email as portalr takes one for an owner: something@something.something, no spaces. */
export const isEmail = (text: string) =>
  text.length <= 254 && /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(text);
