import { Page } from "@portalr/ui";
import { createFileRoute, getRouteApi, Link } from "@tanstack/react-router";

const tenant = getRouteApi("/_signed/t/$tenant");

/** The workspaces the caller can open in the tenant, as grantr lists them. */
export const Route = createFileRoute("/_signed/t/$tenant/")({ component: Workspaces });

function Workspaces() {
  const me = tenant.useLoaderData();
  return (
    <Page title={me.tenant}>
      {me.workspaces.length === 0 ? (
        <p>There is no workspace here you can open.</p>
      ) : (
        <nav aria-label="Workspaces">
          <ul className="flex flex-col gap-2">
            {me.workspaces.map((workspace) => (
              <li key={workspace}>
                <Link
                  to="/t/$tenant/w/$workspace"
                  params={{ tenant: me.tenant, workspace }}
                  className="text-accent underline"
                >
                  {workspace}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      )}
    </Page>
  );
}
