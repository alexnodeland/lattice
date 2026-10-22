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
  /** Whether what is set here is narrowed, so something else applies instead. */
  readonly clamped: boolean;
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
 * A setting's name, from its sentence: a connected app's limit, as lattice declares it, is named
 * by its app, "FreeCAD's tries an hour"; any other by its sentence.
 */
export function nameOf(state: SettingState): string {
  const app = /connected (\S+) a workspace/u.exec(state.description)?.[1];
  return app === undefined ? state.description : `${app}'s tries an hour`;
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
      clamped: here?.clamped ?? false,
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
 * A number field's text as a value: a whole number, or a sentence saying why not, before grantr
 * is asked, so a field says what's wrong as it is left.
 */
export function numberOf(
  text: string,
  kind: SettingState["kind"],
): { value: number } | { error: string } {
  const trimmed = text.trim();
  if (!/^\d{1,9}$/u.test(trimmed)) {
    return { error: "Enter a whole number." };
  }
  const value = Number(trimmed);
  const low = kind.low ?? 0;
  const high = kind.high ?? Number.MAX_SAFE_INTEGER;
  if (value < low || value > high) {
    return { error: `Enter a number from ${low} to ${high}.` };
  }
  return { value };
}
