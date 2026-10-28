/**
 * lattice's integrations, as the UIs read them from grantr (grantr ADR-0034). A workspace's are
 * read once and kept, and where they can't be read, each is its registry default, which
 * `src/generated/integrations.ts` holds, written from lattice-core's `KNOWN`: what is off by
 * default, such as mini apps and Mermaid, stays off (portalr ADR-0045).
 */

import { type QueryClient, useQuery } from "@tanstack/react-query";
import { INTEGRATIONS } from "./generated/integrations";
import { type createQueries, keys } from "./queries";

/** One of lattice's integrations, by its key, such as `markdown:mermaid`. */
export type IntegrationKey = (typeof INTEGRATIONS)[number]["key"];

/** The integrations on where no one has set them. */
const ON_BY_DEFAULT: ReadonlySet<string> = new Set(
  INTEGRATIONS.filter((known) => known.default).map((known) => known.key),
);

/**
 * Whether each integration is on, as grantr answered, or before it answers, or where it can't be
 * read, its default. A key grantr didn't answer for is its default too.
 */
export const enabledFrom =
  (flags: Readonly<Record<string, boolean>> | undefined) =>
  (key: IntegrationKey): boolean =>
    flags?.[key] ?? ON_BY_DEFAULT.has(key);

/** Each integration as it is by default, before a read and where one fails. */
const BY_DEFAULT = enabledFrom(undefined);

/**
 * Whether each integration is on in a workspace, read once and kept, as `enabledIntegrations`
 * says. A failed read is never a reason for a screen to fail: it answers each default, or what
 * was last read. The answer is the same function until what is read changes, so a part that
 * keeps what it was told, such as a form refused as off, can tell a new read from a render.
 */
export function useEnabled(
  queries: ReturnType<typeof createQueries>,
  tenant: string,
  workspace: string,
): (key: IntegrationKey) => boolean {
  // `select` is kept by the query, by what was read, so it answers the same function until then.
  const { data } = useQuery({
    ...queries.grantr.enabledIntegrations(tenant, workspace),
    select: enabledFrom,
  });
  return data ?? BY_DEFAULT;
}

/**
 * An integration's name and what it is, from its sentence: the registry's start with the name,
 * as in "Mermaid: diagrams written as text in messages, drawn."; one that doesn't is named by
 * its key.
 */
export function namedOf(state: { readonly key: string; readonly description: string }): {
  name: string;
  description: string;
} {
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
 * The answer to a setting of an integration, once every read of the tenant's integrations is
 * stale, done or refused: a setting on the tenant changes what each of its workspaces gets.
 */
export async function changedIntegrations<A>(
  queryClient: QueryClient,
  tenant: string,
  answer: Promise<A>,
): Promise<A> {
  const answered = await answer;
  await queryClient.invalidateQueries({ queryKey: keys.grantr.integrations(tenant) });
  return answered;
}
