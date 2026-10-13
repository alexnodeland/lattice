import { administered, adminLanding } from "@portalr/client";
import { Account, Plain, Row, RowLink, Rows } from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute, Link, redirect } from "@tanstack/react-router";
import { lastChoice } from "../../last";

/**
 * Where admin opens: admin's last choice if it is still theirs, their one tenant, every tenant
 * for an operator with none, a choice of those, or no access.
 */
export const Route = createFileRoute("/_signed/")({
  head: () => ({ meta: [{ title: "Tenants · portalr admin" }] }),
  loader: async ({ context }) => {
    const { queries, queryClient, user } = context;
    const [memberships, every] = await Promise.all([
      queryClient.ensureQueryData(queries.grantr.memberships(user)),
      queryClient.ensureQueryData(queries.portalr.tenants()),
    ]);
    const lands = adminLanding(memberships, every !== null, lastChoice());
    if (lands.kind === "tenant") {
      throw redirect({ to: "/t/$tenant", params: { tenant: lands.tenant } });
    }
    if (lands.kind === "deployment") {
      throw redirect({ to: "/deployment" });
    }
  },
  component: Tenants,
});

function Tenants() {
  const { queries, user, signed } = Route.useRouteContext();
  const account = <Account signed={signed} />;
  const { data: memberships } = useSuspenseQuery(queries.grantr.memberships(user));
  const { data: every } = useSuspenseQuery(queries.portalr.tenants());
  const tenants = administered(memberships);
  if (tenants.length === 0 && every === null) {
    return (
      <Plain ui="admin" home={<Link to="/" />} title="No access" account={account}>
        <p>
          admin is for a tenant's owners and admins, and the deployment's operators. You're none of
          these yet.
        </p>
      </Plain>
    );
  }
  return (
    <Plain ui="admin" home={<Link to="/" />} title="Choose a tenant" account={account}>
      <nav aria-label="Tenants">
        <Rows label="Tenants">
          {tenants.map((tenant) => (
            <Row key={tenant}>
              <RowLink render={<Link to="/t/$tenant" params={{ tenant }} />}>{tenant}</RowLink>
            </Row>
          ))}
          {every !== null && (
            <Row>
              <RowLink render={<Link to="/deployment" />}>All tenants</RowLink>
            </Row>
          )}
        </Rows>
      </nav>
    </Plain>
  );
}
