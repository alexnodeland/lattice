/** After a change to who may see and do what, grantr's answers in its tenant are read again. */

import type { QueryClient } from "@tanstack/react-query";
import { keys } from "./queries";

/**
 * The answer to a change of access, once grantr's reads in the tenant are stale: the checks,
 * `/me`, and its members, groups, roles, grants and keys. It is so done or refused, since a
 * refusal may say what changed elsewhere.
 */
export async function changedAccess<A>(
  queryClient: QueryClient,
  tenant: string,
  answer: Promise<A>,
): Promise<A> {
  const answered = await answer;
  await queryClient.invalidateQueries({ queryKey: keys.grantr.tenant(tenant) });
  return answered;
}
