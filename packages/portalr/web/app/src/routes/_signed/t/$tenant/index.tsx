import { Page, TextLink } from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";

/** The workspaces the caller can open in the tenant, as grantr lists them, in order. */
export const Route = createFileRoute("/_signed/t/$tenant/")({ component: Workspaces });

function Workspaces() {
  const { tenant } = Route.useParams();
  const { queries } = Route.useRouteContext();
  const { data: me } = useSuspenseQuery(queries.grantr.me(tenant));
  const workspaces = [...me.workspaces].sort();
  return (
    <Page title={tenant}>
      {workspaces.length === 0 ? (
        <p>There is no workspace here you can open.</p>
      ) : (
        <nav aria-label="Workspaces">
          <ul className="flex flex-col gap-2">
            {workspaces.map((workspace) => (
              <li key={workspace}>
                <TextLink
                  render={<Link to="/t/$tenant/w/$workspace" params={{ tenant, workspace }} />}
                >
                  {workspace}
                </TextLink>
              </li>
            ))}
          </ul>
        </nav>
      )}
    </Page>
  );
}
