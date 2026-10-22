/**
 * The query cache app and admin each keep: a read refused because no one is signed in ends the
 * session, and a read refused for what was asked isn't asked again.
 */

import { QueryCache, QueryClient } from "@tanstack/react-query";
import { Refused, refusedOutright, retryDelay } from "./queries";

/** A query cache whose reads call `unsigned` when one is refused for no one signed in. */
export function createQueryClient(unsigned: () => void): QueryClient {
  return new QueryClient({
    queryCache: new QueryCache({
      onError: (error) => {
        if (error instanceof Refused && error.status === 401) {
          unsigned();
        }
      },
    }),
    defaultOptions: {
      queries: { retry: (count, error) => !refusedOutright(error) && count < 3, retryDelay },
    },
  });
}
