import { administered } from "@portalr/client";
import { NavLink, SideNav } from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute, Link, Outlet, redirect } from "@tanstack/react-router";
import { Building2, House, ScrollText, Wrench } from "lucide-react";
import { Frame } from "../../frame";
import { remember } from "../../last";

/**
 * Every tenant, for the deployment's operators: the deployment's areas alone, with no tenant's
 * (portalr ADR-0021). Anyone else is sent to where admin opens for them.
 */
export const Route = createFileRoute("/_signed/deployment")({
  head: () => ({ meta: [{ title: "All tenants · portalr admin" }] }),
  beforeLoad: async ({ context }) => {
    const { queries, queryClient, user } = context;
    const [, every] = await Promise.all([
      queryClient.ensureQueryData(queries.grantr.memberships(user)),
      queryClient.ensureQueryData(queries.portalr.tenants(user)),
    ]);
    if (every === null) {
      throw redirect({ to: "/" });
    }
  },
  onEnter: () => remember("deployment"),
  component: Deployment,
});

function Deployment() {
  const { queries, user, signed } = Route.useRouteContext();
  const { data: memberships } = useSuspenseQuery(queries.grantr.memberships(user));
  return (
    <Frame
      tenant={null}
      tenants={administered(memberships)}
      operator
      signed={signed}
      nav={
        <SideNav label="Deployment">
          <NavLink icon={House} render={<Link to="/deployment" activeOptions={{ exact: true }} />}>
            Home
          </NavLink>
          <NavLink icon={Building2} render={<Link to="/deployment/tenants" />}>
            Tenants
          </NavLink>
          <NavLink icon={ScrollText} render={<Link to="/deployment/audit" />}>
            Audit
          </NavLink>
          <NavLink icon={Wrench} render={<Link to="/deployment/tools" />}>
            Tools
          </NavLink>
        </SideNav>
      }
    >
      <Outlet />
    </Frame>
  );
}
