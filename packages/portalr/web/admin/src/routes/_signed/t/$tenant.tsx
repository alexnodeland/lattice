import { administered } from "@portalr/client";
import { NavLink, Plain, SideNav, TextLink } from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute, Link, notFound, Outlet } from "@tanstack/react-router";
import { House } from "lucide-react";
import { Frame } from "../../../frame";
import { remember } from "../../../last";

/**
 * A tenant in admin, for its owners and admins: its areas, in admin's frame. Opening one makes
 * it admin's choice next time. Each area shows only where grantr allows its reads.
 */
export const Route = createFileRoute("/_signed/t/$tenant")({
  head: ({ params }) => ({ meta: [{ title: `${params.tenant} · portalr admin` }] }),
  loader: async ({ context, params }) => {
    const { queries, queryClient, user } = context;
    const [memberships] = await Promise.all([
      queryClient.ensureQueryData(queries.grantr.memberships(user)),
      queryClient.ensureQueryData(queries.portalr.tenants()),
    ]);
    if (!administered(memberships).includes(params.tenant)) {
      throw notFound();
    }
    remember(params.tenant);
  },
  notFoundComponent: () => (
    <Plain ui="admin" home={<Link to="/" />} title="Not a tenant you administer">
      <p>admin shows a tenant to its owners and admins alone.</p>
      <TextLink render={<Link to="/" />}>Choose another</TextLink>
    </Plain>
  ),
  component: Tenant,
});

function Tenant() {
  const { tenant } = Route.useParams();
  const { queries, user, signed } = Route.useRouteContext();
  const { data: memberships } = useSuspenseQuery(queries.grantr.memberships(user));
  const { data: every } = useSuspenseQuery(queries.portalr.tenants());
  return (
    <Frame
      tenant={tenant}
      tenants={administered(memberships)}
      operator={every !== null}
      signed={signed}
      nav={
        <SideNav label="Tenant">
          <NavLink
            icon={House}
            render={<Link to="/t/$tenant" params={{ tenant }} activeOptions={{ exact: true }} />}
          >
            Home
          </NavLink>
        </SideNav>
      }
    >
      <Outlet />
    </Frame>
  );
}
