import { Page, TextLink } from "@portalr/ui";
import { createFileRoute, Link, Outlet } from "@tanstack/react-router";
import { WorkspaceStreams } from "../../../../../workspace";

/** A workspace: its streams, open while any of its areas is, and the way between its areas. */
export const Route = createFileRoute("/_signed/t/$tenant/w/$workspace")({
  head: ({ params }) => ({ meta: [{ title: `${params.workspace} · ${params.tenant} · portalr` }] }),
  component: Workspace,
});

function Workspace() {
  const { tenant, workspace } = Route.useParams();
  const { config, signed } = Route.useRouteContext();
  return (
    <Page title={workspace}>
      <nav aria-label="Workspace" className="mb-4 flex gap-4">
        <TextLink render={<Link to="/t/$tenant" params={{ tenant }} />}>
          Every workspace in {tenant}
        </TextLink>
        <TextLink render={<Link to="/t/$tenant/w/$workspace" params={{ tenant, workspace }} />}>
          Threads
        </TextLink>
        <TextLink
          render={<Link to="/t/$tenant/w/$workspace/artifacts" params={{ tenant, workspace }} />}
        >
          Artifacts
        </TextLink>
        <TextLink
          render={<Link to="/t/$tenant/w/$workspace/proposals" params={{ tenant, workspace }} />}
        >
          Proposals
        </TextLink>
        <TextLink
          render={<Link to="/t/$tenant/w/$workspace/runs" params={{ tenant, workspace }} />}
        >
          Runs
        </TextLink>
      </nav>
      <WorkspaceStreams
        key={`${tenant}/${workspace}`}
        surfaces={config.surfaces}
        signed={signed}
        tenant={tenant}
        workspace={workspace}
      >
        <Outlet />
      </WorkspaceStreams>
    </Page>
  );
}
