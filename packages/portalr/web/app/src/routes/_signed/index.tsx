import { Page, TextLink } from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute, Link, redirect } from "@tanstack/react-router";
import { landing } from "../../landing";

/** Where a signed-in person lands: their one tenant, a choice of several, or no access. */
export const Route = createFileRoute("/_signed/")({
  head: () => ({ meta: [{ title: "Tenants · portalr" }] }),
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
  const { data } = useSuspenseQuery(queries.grantr.memberships(user));
  const lands = landing(data);
  if (lands.kind !== "choose") {
    return (
      <Page title="No access">
        <p>You aren't a member of any tenant yet. Ask an owner of one to invite you.</p>
      </Page>
    );
  }
  return (
    <Page title="Choose a tenant">
      <nav aria-label="Tenants">
        <ul className="flex flex-col gap-2">
          {lands.tenants.map((tenant) => (
            <li key={tenant}>
              <TextLink render={<Link to="/t/$tenant" params={{ tenant }} />}>{tenant}</TextLink>
            </li>
          ))}
        </ul>
      </nav>
    </Page>
  );
}
