/**
 * The query cache app and admin each keep: a read refused because no one is signed in ends the
 * session, and a read refused for what was asked isn't asked again.
 */

import { QueryCache, QueryClient } from "@tanstack/react-query";
import { Refused } from "./queries";

/** Whether the server refused a read for what was asked: asking again would get the same. */
const refusedOutright = (error: unknown) =>
  error instanceof Refused && error.status >= 400 && error.status < 500;

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
      queries: { retry: (count, error) => !refusedOutright(error) && count < 3 },
    },
  });
}
