/**
 * What a person may do in a workspace, as grantr's `/checks` answers, so a screen shows only the
 * actions they can take. The server checks each command again when it arrives: hiding a button
 * is no permission.
 */

import type { createQueries, GrantrApi } from "@portalr/client";

type Resource = GrantrApi.components["schemas"]["Resource"];

/** A workspace, as grantr names one. */
export const workspaceOf = (workspace: string): Resource => ({ kind: "workspace", workspace });

/**
 * One read of grantr's checks for these actions on a resource, answered as the allowed ones: a
 * workspace, or something in it, such as a thread or a rule, as the server will check them.
 */
export function allowedIn(
  queries: ReturnType<typeof createQueries>,
  tenant: string,
  resource: Resource,
  actions: readonly string[],
) {
  const checks = actions.map((action) => ({ action, resource }));
  return {
    ...queries.grantr.checks(tenant, checks),
    select: (answers: boolean[]) =>
      new Set(actions.filter((_action, index) => answers[index] === true)),
  };
}
