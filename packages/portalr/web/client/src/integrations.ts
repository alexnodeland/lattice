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

/**
 * Whether each integration is on in a workspace, read once and kept, as `enabledIntegrations`
 * says. A failed read is never a reason for a screen to fail: it answers each default, or what
 * was last read.
 */
export function useEnabled(
  queries: ReturnType<typeof createQueries>,
  tenant: string,
  workspace: string,
): (key: IntegrationKey) => boolean {
  const { data } = useQuery(queries.grantr.enabledIntegrations(tenant, workspace));
  return enabledFrom(data);
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
