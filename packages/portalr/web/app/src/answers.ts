/**
 * A person's answer to a question of the relay's, such as analytics' and replay's: read once and
 * shared by every screen that uses it, and recorded with the switch showing it at once.
 */

import { type Api, type Consent, NOT_READ } from "@portalr/client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

/** How often an answer whose deletion isn't done yet is read again, until it is, in ms. */
const UNTIL_DELETED = 30_000;

/**
 * An answer under `key`, as the relay reads it with `read`, where `enabled`: a read that fails
 * keeps the last answer read, or `NOT_READ`. With `poll` it is read again while a deletion is owed,
 * so the note goes when the relay has done it. With `fresh` it is never believed for long: it is
 * read again when the window is focused, so another tab's withdrawal is seen.
 */
export function useRead(
  api: Api,
  key: readonly unknown[],
  read: (api: Api) => Promise<Consent>,
  enabled: boolean,
  poll: boolean,
  fresh = false,
): Consent {
  const { data = NOT_READ } = useQuery({
    queryKey: key,
    queryFn: () => read(api),
    enabled,
    staleTime: fresh ? 0 : Number.POSITIVE_INFINITY,
    refetchOnWindowFocus: fresh ? "always" : true,
    refetchInterval: (query) => (poll && query.state.data?.deleting ? UNTIL_DELETED : false),
  });
  return data;
}

/**
 * Recording an answer under `key`, with `record`: the switch is the answer at once, and goes back
 * to the one the relay has where it isn't recorded (`failed`). Without `optimistic` it shows the
 * answer only once the relay has it. The keys in `also` are read again once it settles.
 */
export function useAnswering(
  api: Api,
  key: readonly unknown[],
  record: (api: Api, answer: boolean) => Promise<unknown>,
  optimistic = true,
  also: readonly (readonly unknown[])[] = [],
) {
  const client = useQueryClient();
  const { mutate, isError } = useMutation({
    mutationFn: (answer: boolean) => record(api, answer),
    onMutate: async (answer: boolean) => {
      await client.cancelQueries({ queryKey: key });
      const before = client.getQueryData<Consent>(key);
      if (optimistic) {
        // A deletion owed stays owed whatever the answer: the relay says when it is done.
        client.setQueryData<Consent>(key, { given: answer, deleting: before?.deleting ?? false });
      }
      return { before };
    },
    // Not recorded: the switch goes back to the answer the relay has, and the status says so.
    onError: (_error, _answer, context) => optimistic && client.setQueryData(key, context?.before),
    onSettled: () =>
      Promise.all([key, ...also].map((queryKey) => client.invalidateQueries({ queryKey }))),
  });
  return { answer: mutate, failed: isError };
}
