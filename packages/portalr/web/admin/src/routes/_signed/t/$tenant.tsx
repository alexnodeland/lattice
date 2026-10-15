import { administered } from "@portalr/client";
import { Account, NavLink, Plain, SideNav, TextLink } from "@portalr/ui";
import { useQuery, useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute, Link, notFound, Outlet } from "@tanstack/react-router";
import { Coins, House, KeyRound, ScrollText, ThumbsUp } from "lucide-react";
import { allowedNow, anyPart, useAccess } from "../../../access";
import { Frame } from "../../../frame";
import { remember } from "../../../last";

/**
 * A tenant in admin, for its owners and admins: its areas, in admin's frame. Who may open it is
 * settled before any of its routes load, and opening it makes it admin's choice next time. Each
 * area shows only where grantr allows its reads.
 */
export const Route = createFileRoute("/_signed/t/$tenant")({
  head: ({ params }) => ({ meta: [{ title: `${params.tenant} · portalr admin` }] }),
  beforeLoad: async ({ context, params }) => {
    const { queries, queryClient, user } = context;
    const memberships = await queryClient.ensureQueryData(queries.grantr.memberships(user));
    if (!administered(memberships).includes(params.tenant)) {
      throw notFound();
    }
    // What its rail shows: Access, where grantr allows one of its parts.
    await allowedNow(context, params.tenant);
  },
  // Entering it, or switching to another tenant on it, makes it the choice.
  onEnter: ({ params }) => remember(params.tenant),
  onStay: ({ params }) => remember(params.tenant),
  notFoundComponent: NotAdministered,
  component: Tenant,
});

function NotAdministered() {
  const { signed } = Route.useRouteContext();
  return (
    <Plain
      ui="admin"
      home={<Link to="/" />}
      title="Not a tenant you administer"
      account={<Account signed={signed} />}
    >
      <p>admin shows a tenant to its owners and admins alone.</p>
      <TextLink render={<Link to="/" />}>Choose another</TextLink>
    </Plain>
  );
}

function Tenant() {
  const { tenant } = Route.useParams();
  const { queries, user, signed } = Route.useRouteContext();
  const { data: memberships } = useSuspenseQuery(queries.grantr.memberships(user));
  // Whether they may see every tenant, for the switch alone: a tenant's admin needn't wait on it.
  const { data: every } = useQuery(queries.portalr.tenants(user));
  const { allowed } = useAccess(tenant);
  return (
    <Frame
      tenant={tenant}
      tenants={administered(memberships)}
      operator={every !== null && every !== undefined}
      signed={signed}
      nav={
        <SideNav label="Tenant">
          <NavLink
            icon={House}
            render={<Link to="/t/$tenant" params={{ tenant }} activeOptions={{ exact: true }} />}
          >
            Home
          </NavLink>
          {anyPart(allowed) && (
            <NavLink icon={KeyRound} render={<Link to="/t/$tenant/access" params={{ tenant }} />}>
              Access
            </NavLink>
          )}
          {allowed.has("grantr:read_audit") && (
            <NavLink icon={ScrollText} render={<Link to="/t/$tenant/audit" params={{ tenant }} />}>
              Audit
            </NavLink>
          )}
          {allowed.has("portalr:read_telemetry") && (
            <NavLink icon={ThumbsUp} render={<Link to="/t/$tenant/feedback" params={{ tenant }} />}>
              Feedback
            </NavLink>
          )}
          {allowed.has("portalr:read_spend") && (
            <NavLink icon={Coins} render={<Link to="/t/$tenant/usage" params={{ tenant }} />}>
              Usage
            </NavLink>
          )}
        </SideNav>
      }
    >
      <Outlet />
    </Frame>
  );
}
