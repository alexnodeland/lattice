import { Page } from "@portalr/ui";
import { createFileRoute, Link, redirect } from "@tanstack/react-router";
import { landing } from "../../landing";

/** Where a signed-in person lands: their one tenant, a choice of several, or no access. */
export const Route = createFileRoute("/_signed/")({
  beforeLoad: ({ context }) => {
    context.signed.tenant = null;
  },
  loader: async ({ context }) => {
    const lands = landing(
      await context.queryClient.ensureQueryData(context.queries.grantr.memberships()),
    );
    if (lands.kind === "tenant") {
      throw redirect({ to: "/t/$tenant", params: { tenant: lands.tenant } });
    }
    return lands;
  },
  component: Tenants,
});

function Tenants() {
  const lands = Route.useLoaderData();
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
              <Link to="/t/$tenant" params={{ tenant }} className="text-accent underline">
                {tenant}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
    </Page>
  );
}
