import { Page } from "@portalr/ui";
import { createFileRoute, Link } from "@tanstack/react-router";

/** A workspace, which the app's areas open into. */
export const Route = createFileRoute("/_signed/t/$tenant/w/$workspace")({ component: Workspace });

function Workspace() {
  const { tenant, workspace } = Route.useParams();
  return (
    <Page title={workspace}>
      <Link to="/t/$tenant" params={{ tenant }} className="text-accent underline">
        Every workspace in {tenant}
      </Link>
    </Page>
  );
}
