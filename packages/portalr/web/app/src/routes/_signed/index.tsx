import { landing } from "@portalr/client";
import { Plain, Row, RowLink, Rows } from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute, Link, redirect } from "@tanstack/react-router";
import { AppAccount } from "../../analytics";

/** Where a signed-in person lands: their one tenant, a choice of several, or no access. */
export const Route = createFileRoute("/_signed/")({
  head: ({ match }) => ({
    meta: [{ title: match.context.title("Tenants") }],
  }),
  loader: async ({ context }) => {
    const memberships = context.queries.grantr.memberships(context.user);
    const lands = landing(await context.queryClient.ensureQueryData(memberships));
    if (lands.kind === "tenant") {
      throw redirect({ to: "/t/$tenant", params: { tenant: lands.tenant } });
    }
  },
  component: Tenants,
});

function Tenants() {
  const { queries, user } = Route.useRouteContext();
  const account = <AppAccount />;
  const { data } = useSuspenseQuery(queries.grantr.memberships(user));
  const lands = landing(data);
  if (lands.kind !== "choose") {
    return (
      <Plain home={<Link to="/" />} title="No access" account={account}>
        <p>You aren't a member of any tenant yet. Ask an owner of one to invite you.</p>
      </Plain>
    );
  }
  return (
    <Plain home={<Link to="/" />} title="Choose a tenant" account={account}>
      <nav aria-label="Tenants">
        <Rows label="Tenants">
          {lands.tenants.map((tenant) => (
            <Row
              key={tenant}
              name={
                <RowLink render={<Link to="/t/$tenant" params={{ tenant }} />}>{tenant}</RowLink>
              }
            />
          ))}
        </Rows>
      </nav>
    </Plain>
  );
}
