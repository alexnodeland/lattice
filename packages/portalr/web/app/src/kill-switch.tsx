/**
 * While a mini app runs, the workspace's integrations are read again every half minute, so an
 * operator, a tenant's admin or a workspace's switching mini apps off stops it soon, as archiving
 * it does at once (portalr ADR-0051).
 */

import { useQuery } from "@tanstack/react-query";
import type { Context } from "./context";

export function KillSwitch({
  queries,
  tenant,
  workspace,
}: {
  queries: Context["queries"];
  tenant: string;
  workspace: string;
}) {
  useQuery({ ...queries.grantr.enabledIntegrations(tenant, workspace), refetchInterval: 30_000 });
  return null;
}
