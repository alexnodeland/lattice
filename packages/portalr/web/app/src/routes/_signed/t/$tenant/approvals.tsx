import { AppShell, Switcher } from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute, Link, Outlet, useNavigate } from "@tanstack/react-router";
import { AppAccount } from "../../../../analytics";

/**
 * The tenant's approvals, in the frame the tenant's workspaces are listed in: the way between
 * tenants and workspaces, and the account. Approvals come from every workspace, so no workspace's
 * frame holds them (grantr ADR-0040).
 */
export const Route = createFileRoute("/_signed/t/$tenant/approvals")({
  loader: ({ context }) =>
    context.queryClient.ensureQueryData(context.queries.grantr.memberships(context.user)),
  component: Approvals,
});

function Approvals() {
  const { tenant } = Route.useParams();
  const { queries, user } = Route.useRouteContext();
  const navigate = useNavigate();
  const { data: memberships } = useSuspenseQuery(queries.grantr.memberships(user));
  const { data: me } = useSuspenseQuery(queries.grantr.me(tenant));
  const tenants = [...new Set(memberships.map((membership) => membership.tenant))].sort();
  return (
    <AppShell
      home={<Link to="/" />}
      switcher={
        <Switcher
          tenant={tenant}
          tenants={tenants.map((id) => ({ id }))}
          workspaces={[...me.workspaces].sort().map((id) => ({ id }))}
          onTenant={(id) => void navigate({ to: "/t/$tenant/approvals", params: { tenant: id } })}
          onWorkspace={(id) =>
            void navigate({ to: "/t/$tenant/w/$workspace", params: { tenant, workspace: id } })
          }
        />
      }
      account={<AppAccount />}
    >
      <Outlet />
    </AppShell>
  );
}
