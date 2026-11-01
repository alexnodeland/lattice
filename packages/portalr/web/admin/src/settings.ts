/**
 * Settings' words (portalr ADR-0067): each setting at a level, the tenant or one of its
 * workspaces, as grantr answers it there (lattice ADR-0030): what applies, how far this level may
 * go and which layer says so, what is set here and by whom, and whether something narrower
 * applies instead.
 */

import { type createQueries, type GrantrApi, type Names, workspaceOf } from "@portalr/client";
import { actor } from "./audit";

type SettingState = GrantrApi.components["schemas"]["SettingState"];
type Value = SettingState["effective"];

/** One setting as the page shows it. */
export interface SettingRow {
  readonly key: string;
  /** Its name, for its field's label: what it limits, never its key. */
  readonly name: string;
  readonly description: string;
  readonly kind: SettingState["kind"];
  /** What applies at this level, said, and as it is. */
  readonly effective: string;
  readonly effectiveValue: Value;
  /** How far this level may go, and which layer says so: at most, or a superset's at least. */
  readonly ceiling: string;
  readonly ceilingValue: Value;
  /** Who sets the ceiling, for a choice it leaves out: "the operator", "the tenant". */
  readonly ceilingBy: string;
  /** What is set at this level, or null where nothing is. */
  readonly here: { readonly value: Value; readonly by: string; readonly at: string } | null;
  /** Why what is set here doesn't apply, where something else does; null where it applies. */
  readonly clamped: string | null;
  /** The lowest and highest values its kind takes, where it is a number. */
  readonly low: number | null;
  readonly high: number | null;
  /** The version a change names: what this level's setting was read at. */
  readonly version: number;
  /** What unsetting it here falls back to: the tenant's value, the operator's, or the default. */
  readonly inherits: string;
}

/** A value as a sentence says it: a number, or names joined. */
export const said = (value: number | readonly string[]): string =>
  typeof value === "number" ? `${value}` : value.length > 0 ? value.join(", ") : "none";

const SETTERS = {
  default: "the default",
  operator: "the operator's value",
  tenant: "the tenant's value",
} as const;

/**
 * Each setting's name, by its key: what it limits, for its field's label and for every sentence
 * that names it, never its key. A test holds that every setting lattice-core declares has one.
 */
const LABELS: Readonly<Record<string, string>> = {
  "connect-per-hour:freecad": "FreeCAD's tries an hour",
  "connect-per-hour:blender": "Blender's tries an hour",
  "connect-tools:freecad": "FreeCAD's tools",
  "connect-tools:blender": "Blender's tools",
  "agent-writes:direct": "Kinds the agent edits directly in Auto",
  "approve:tiers": "Tiers that need approval",
  "approve-within": "Minutes an approval waits for an answer",
  "admin-high:different-approver": "Admin actions a second person approves",
};

/** A setting's name: its label, or, for one this admin doesn't know yet, its sentence. */
export const nameOf = (state: SettingState): string => LABELS[state.key] ?? state.description;

/**
 * Why what is set here doesn't apply: the settings now allow no less than it, or a layer above,
 * or the settings, allow no more, or, for a superset, a layer above asks for more.
 */
function clampedOf(state: SettingState, value: Value): string {
  const low = state.kind.low;
  if (typeof value === "number" && low != null && value < low) {
    return `The settings now allow at least ${low}: ${said(state.effective)} applies.`;
  }
  if (state.kind.type === "superset") {
    return `What is set here doesn't apply: ${said(state.effective)} does, as more is asked for now.`;
  }
  return `What is set here doesn't apply: ${said(state.effective)} does, as no more is allowed now.`;
}

/** How far a level may go: at most the layer above's, or, for a superset, at least it. */
const boundOf = (state: SettingState): string =>
  `${state.kind.type === "superset" ? "At least" : "At most"} ${said(state.ceiling)}: ${SETTERS[state.ceiling_set_by]}.`;

/** Each setting at a level as the page shows it, with who set it there named as `names` does. */
export function settingRowsOf(
  states: readonly SettingState[],
  workspace: boolean,
  names: Names,
): SettingRow[] {
  return states.map((state) => {
    const here = workspace ? state.workspace : state.tenant;
    return {
      key: state.key,
      name: nameOf(state),
      description: state.description,
      kind: state.kind,
      effective: said(state.effective),
      effectiveValue: state.effective,
      ceiling: boundOf(state),
      ceilingValue: state.ceiling,
      ceilingBy: { default: "the deployment", operator: "the operator", tenant: "the tenant" }[
        state.ceiling_set_by
      ],
      here: here ? { value: here.value, by: actor(here.by, names), at: here.at } : null,
      clamped: here?.clamped ? clampedOf(state, here.value) : null,
      low: state.kind.low ?? null,
      high: state.kind.high ?? null,
      version: state.version,
      inherits: workspace
        ? "the tenant's"
        : state.operator === null
          ? "the default"
          : "the operator's",
    };
  });
}

/** The ids of the people who set each setting at a level: the ones whose emails it asks for. */
export const settersOf = (states: readonly SettingState[], workspace: boolean) =>
  states.flatMap((state) => {
    const by = (workspace ? state.workspace : state.tenant)?.by;
    return by?.kind === "user" ? [by.id] : [];
  });

/**
 * A number field's text as a value: a whole number within its kind's bounds, or a sentence saying
 * why not, before grantr is asked. How far this level may go is grantr's to say, with the layer
 * that sets it.
 */
export function numberOf(
  text: string,
  low: number,
  high: number,
): { value: number } | { error: string } {
  const trimmed = text.trim();
  if (!/^\d{1,9}$/u.test(trimmed)) {
    return { error: `Enter a whole number from ${low} to ${high}.` };
  }
  const value = Number(trimmed);
  if (value < low || value > high) {
    return { error: `Enter a whole number from ${low} to ${high}.` };
  }
  return { value };
}

/** Where a person may narrow settings: on the tenant, and in which of its workspaces. */
export interface Places {
  readonly tenant: boolean;
  readonly workspaces: readonly string[];
  /**
   * Whether some workspaces weren't asked about: one read of grantr's checks asks about the
   * tenant and the first 99 by name, so a workspace's admin of a later one isn't told of it here.
   */
  readonly cut: boolean;
}

/** The most workspaces one read of grantr's checks asks about: its batch's most, but the tenant. */
export const MOST_ASKED = 99;

/**
 * One read of grantr's checks: whether the person holds `grantr:manage_settings` on the tenant and
 * in each of its first 99 workspaces (issue 627). Held on the tenant, it covers every workspace, so
 * all of them are theirs, past the 99 too; grantr checks each change again. A workspace's admins
 * hold it in theirs alone.
 */
export function settingsPlaces(
  queries: ReturnType<typeof createQueries>,
  tenant: string,
  workspaces: readonly string[],
) {
  const sorted = [...workspaces].sort();
  const asked = sorted.slice(0, MOST_ASKED);
  const action = "grantr:manage_settings";
  const checks = [
    { action, resource: { kind: "tenant" as const } },
    ...asked.map((name) => ({ action, resource: workspaceOf(name) })),
  ];
  return {
    ...queries.grantr.checks(tenant, checks),
    select: (answers: boolean[]): Places =>
      answers[0] === true
        ? { tenant: true, workspaces: sorted, cut: false }
        : {
            tenant: false,
            workspaces: asked.filter((_name, at) => answers[at + 1] === true),
            cut: sorted.length > asked.length,
          },
  };
}

/** Whether a person may narrow settings anywhere in the tenant: whether Settings joins the rail. */
export const anywhere = (places: Places) => places.tenant || places.workspaces.length > 0;

/**
 * Why grantr refused to set a value, in the page's words from what the page shows, never grantr's
 * own (portalr ADR-0070): a number over the ceiling is told the ceiling and who set it; a choice
 * of tools, that only what the ceiling offers may be checked; any other value refused, that it
 * isn't allowed; a 403, that it can't be changed here.
 */
export function refusedWhy(row: SettingRow, status: number, tried: number | null): string {
  return `${row.name} wasn't changed: ${whyRefused(row, status, tried)}`;
}

function whyRefused(row: SettingRow, status: number, tried: number | null): string {
  if (status === 403) {
    return "it can't be changed here.";
  }
  if (status === 401) {
    return "you're not signed in. Sign in, then try again.";
  }
  if (status !== 422) {
    return "the server couldn't do it just now. Try again in a moment.";
  }
  if (Array.isArray(row.ceilingValue)) {
    return `only what ${row.ceilingBy} offers may be checked here.`;
  }
  const over = typeof row.ceilingValue === "number" && tried !== null && tried > row.ceilingValue;
  return over
    ? `it may be at most ${said(row.ceilingValue)} here, as ${row.ceilingBy} set it.`
    : "that value isn't allowed here.";
}
