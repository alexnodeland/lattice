import { Refused } from "@portalr/client";
import { Plain, TextLink } from "@portalr/ui";
import { createFileRoute, Link, notFound, Outlet } from "@tanstack/react-router";
import { useGiven, usePageViews, useReplay } from "../../../analytics";

/** A tenant: grantr says who the caller is in it, and every read under it names it. */
export const Route = createFileRoute("/_signed/t/$tenant")({
  head: ({ params, match }) => ({
    meta: [
      {
        title: match.context.title(
          match.status === "notFound" ? "Tenant not found" : params.tenant,
        ),
      },
    ],
  }),
  loader: async ({ context, params }) => {
    try {
      return await context.queryClient.ensureQueryData(context.queries.grantr.me(params.tenant));
    } catch (error) {
      // A tenant the caller isn't a member of is, to them, not there (portalr ADR-0068).
      if (error instanceof Refused && (error.status === 403 || error.status === 404)) {
        throw notFound();
      }
      throw error;
    }
  },
  notFoundComponent: NoSuchTenant,
  component: Tenant,
});

/**
 * A tenant that isn't there, to the reader. A page that isn't there under one that is is `$.tsx`'s
 * (portalr ADR-0068).
 */
function NoSuchTenant() {
  return (
    <Plain home={<Link to="/" />} title="Tenant not found">
      <p>There's no tenant here by that name, or you aren't in it.</p>
      <TextLink render={<Link to="/" />}>Choose a tenant</TextLink>
    </Plain>
  );
}

/** The tenant's pages, each counted as the person opens it, and recorded, with their yes. */
function Tenant() {
  const { api, config, user } = Route.useRouteContext();
  const { tenant } = Route.useParams();
  const given = useGiven();
  usePageViews(api, tenant, given);
  const replay = useReplay(config.replay === true);
  return (
    <>
      <Outlet />
      {replay && <replay.Recording api={api} user={user} tenant={tenant} analytics={given} />}
    </>
  );
}
