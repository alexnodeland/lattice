/**
 * What a person may do in a workspace, as grantr's `/checks` answers, so a screen shows only the
 * actions they can take. The server checks each command again when it arrives: hiding a button
 * is no permission.
 */

import type { createQueries } from "@portalr/client";

/** One read of grantr's checks for these actions in a workspace, answered as the allowed ones. */
export function allowedIn(
  queries: ReturnType<typeof createQueries>,
  tenant: string,
  workspace: string,
  actions: readonly string[],
) {
  const checks = actions.map((action) => ({
    action,
    resource: { kind: "workspace" as const, workspace },
  }));
  return {
    ...queries.grantr.checks(tenant, checks),
    select: (answers: boolean[]) =>
      new Set(actions.filter((_action, index) => answers[index] === true)),
  };
}
