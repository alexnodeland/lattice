/**
 * People by email, not by the id grantr knows them by (portalr ADR-0036).
 *
 * With real Supabase a person's id is their auth user's UUID. The server names the ones the
 * reader may see, so a screen asks for the ids it shows and calls what comes back a `Names`:
 * the email, or a short id where there is none. An email is personal data: it is kept in the
 * query cache's memory alone, and never in the address, a store, the stream or a log.
 */

import { useQuery } from "@tanstack/react-query";
import type { createQueries } from "./queries";

/** Names a person: their email where it is known, otherwise a short form of their id. */
export type Names = (id: string) => string;

/** How long an id is shown before it is cut short: a UUID, or anything as long. */
const SHORT_FROM = 16;

/** How many characters of a long id are shown. */
const SHORT = 8;

/** An id as short as it can be told apart: long ids, such as a UUID, to their first eight. */
export const shortId = (id: string): string =>
  id.length >= SHORT_FROM ? `${id.slice(0, SHORT)}…` : id;

/** The names of the people `emails` holds, by id, and a short id for anyone else. */
export function namesOf(emails: Readonly<Record<string, string>> | undefined): Names {
  return (id) => emails?.[id] ?? shortId(id);
}

/**
 * What to show while a new set of ids is read: the last set's emails, so a name does not flicker
 * to a short id as a list changes, but only the same tenant's (or the deployment's): a tenant's
 * emails are gone the moment another is opened.
 */
export const keepWithin =
  (tenant: string | null) =>
  <D>(previous: D | undefined, query: { readonly queryKey: readonly unknown[] } | undefined) =>
    query?.queryKey[1] === (tenant ?? "~deployment") ? previous : undefined;

/**
 * The names of `ids` in `tenant`, as the server lets the reader see them: read once for the set,
 * kept in memory for a few minutes, and never a reason for a screen to fail. Until they come, and
 * wherever the server names no one, a person is their short id. `enabled` is `config.people`.
 */
export function usePeople(
  queries: ReturnType<typeof createQueries>,
  enabled: boolean,
  tenant: string | null,
  ids: Iterable<string>,
): Names {
  const unique = [...new Set(ids)].sort();
  const { data } = useQuery({
    ...queries.portalr.people(tenant, unique),
    enabled: enabled && unique.length > 0,
    placeholderData: keepWithin(tenant),
  });
  return namesOf(data);
}
