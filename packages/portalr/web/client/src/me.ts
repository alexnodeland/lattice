/** Who the reader is, as the server attributes their messages and feedback in a tenant. */

import { useSuspenseQuery } from "@tanstack/react-query";
import type { createQueries } from "./queries";

/** The id grantr knows the signed-in person, `user`, by in `tenant`, from their memberships. */
export function useMe(
  queries: ReturnType<typeof createQueries>,
  user: string,
  tenant: string,
): string {
  const { data } = useSuspenseQuery(queries.grantr.memberships(user));
  return data.find((membership) => membership.tenant === tenant)?.user ?? user;
}
