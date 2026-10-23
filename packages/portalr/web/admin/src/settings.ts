/**
 * Settings' words (portalr ADR-0067): each setting at a level, the tenant or one of its
 * workspaces, as grantr answers it there (lattice ADR-0030): what applies, how far this level may
 * go and which layer says so, what is set here and by whom, and whether something narrower
 * applies instead.
 */

import type { GrantrApi, Names } from "@portalr/client";
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
  /** What applies at this level. */
  readonly effective: string;
  /** How far this level may go, and which layer says so. */
  readonly ceiling: string;
  readonly ceilingValue: Value;
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
export const said = (value: Value): string =>
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
};

/** A setting's name: its label, or, for one this admin doesn't know yet, its sentence. */
export const nameOf = (state: SettingState): string => LABELS[state.key] ?? state.description;

/**
 * Why what is set here doesn't apply: the settings now allow no less than it, or a layer above,
 * or the settings, allow no more.
 */
function clampedOf(state: SettingState, value: Value): string {
  const low = state.kind.low;
  if (typeof value === "number" && low != null && value < low) {
    return `The settings now allow at least ${low}: ${said(state.effective)} applies.`;
  }
  return `What is set here doesn't apply: ${said(state.effective)} does, as no more is allowed now.`;
}

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
      ceiling: `At most ${said(state.ceiling)}: ${SETTERS[state.ceiling_set_by]}.`,
      ceilingValue: state.ceiling,
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

/** grantr's refusal of a setting as the field says it: its key named as the page names it. */
export const refusedAs = (reason: string, row: { readonly key: string; readonly name: string }) =>
  reason.replaceAll(row.key, row.name);
