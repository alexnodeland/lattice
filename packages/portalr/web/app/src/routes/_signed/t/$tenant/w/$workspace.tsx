import { Page, TextLink } from "@portalr/ui";
import { createFileRoute, Link } from "@tanstack/react-router";

/** A workspace, which the app's areas open into. */
export const Route = createFileRoute("/_signed/t/$tenant/w/$workspace")({
  head: ({ params }) => ({ meta: [{ title: `${params.workspace} · ${params.tenant} · portalr` }] }),
  component: Workspace,
});

function Workspace() {
  const { tenant, workspace } = Route.useParams();
  return (
    <Page title={workspace}>
      <TextLink render={<Link to="/t/$tenant" params={{ tenant }} />}>
        Every workspace in {tenant}
      </TextLink>
    </Page>
  );
}
