/**
 * Integrations' address and words (portalr ADR-0045): the level shown, the tenant or one of its
 * workspaces, and each integration as grantr answers it there, as the list shows it: on or off,
 * where that comes from, and who set it at that level.
 */

import type { GrantrApi, Names } from "@portalr/client";
import type { IntegrationRow, IntegrationSource } from "@portalr/ui";
import { actor } from "./audit";
import { nameOf } from "./runs";

type IntegrationState = GrantrApi.components["schemas"]["IntegrationState"];

/** What Integrations' address keeps: a workspace, or none for the tenant. */
export type Level = { readonly workspace?: string | undefined };

/** The address's level: a workspace's name as grantr takes one, or the tenant. */
export const levelOf = (search: Record<string, unknown>): Level => ({
  workspace: nameOf(search.workspace),
});

/**
 * Where an integration's state at a level comes from. A ceiling first, as grantr decides: not
 * installed, then, in a workspace, the tenant's off; then a setting at this level; then, in a
 * workspace, the tenant's; then the default (grantr ADR-0034).
 */
export function sourceOf(state: IntegrationState, workspace: boolean): IntegrationSource {
  if (!state.installed) {
    return "not-installed";
  }
  if (workspace && state.tenant?.on === false) {
    return "tenant-off";
  }
  const here = workspace ? state.workspace : state.tenant;
  if (here) {
    return "set";
  }
  return workspace && state.tenant ? "inherited" : "default";
}

/**
 * An integration's name and what it is, from its sentence: the registry's start with the name,
 * as in "Mermaid: diagrams written as text in messages, drawn."; one that doesn't is named by
 * its key.
 */
export function namedOf(state: IntegrationState): { name: string; description: string } {
  const at = state.description.indexOf(": ");
  if (at < 1) {
    return { name: state.key, description: state.description };
  }
  const rest = state.description.slice(at + 2);
  return {
    name: state.description.slice(0, at),
    description: rest.charAt(0).toUpperCase() + rest.slice(1),
  };
}

/**
 * Each integration at a level as the list shows it, with who set it there named as `names` does,
 * and, where it is on and brings an app at an address of `links`, the way to open it.
 */
export function rowsOf(
  states: readonly IntegrationState[],
  workspace: boolean,
  names: Names,
  links: Readonly<Record<string, string>> = {},
): IntegrationRow[] {
  return states.map((state) => {
    const here = workspace ? state.workspace : state.tenant;
    return {
      key: state.key,
      ...namedOf(state),
      on: state.enabled,
      source: sourceOf(state, workspace),
      changed: here ? { by: actor(here.by, names), at: here.at } : null,
      open: state.enabled ? links[state.key] : undefined,
    };
  });
}

/** The ids of the people who set an integration at a level: the ones whose emails it asks for. */
export const settersOf = (states: readonly IntegrationState[], workspace: boolean) =>
  states.flatMap((state) => {
    const by = (workspace ? state.workspace : state.tenant)?.by;
    return by?.kind === "user" ? [by.id] : [];
  });
