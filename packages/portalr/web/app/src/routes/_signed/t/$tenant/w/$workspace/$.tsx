import { ButtonLink, NotFound } from "@portalr/ui";
import { createFileRoute, Link } from "@tanstack/react-router";

/** A page that isn't there, in a workspace: in its frame (portalr ADR-0068). */
export const Route = createFileRoute("/_signed/t/$tenant/w/$workspace/$")({
  head: ({ match, params }) => ({
    meta: [{ title: match.context.title(`Page not found · ${params.workspace}`) }],
  }),
  component: PageNotFound,
});

function PageNotFound() {
  const { tenant, workspace } = Route.useParams();
  return (
    <NotFound
      title="Page not found"
      action={
        <ButtonLink render={<Link to="/t/$tenant/w/$workspace" params={{ tenant, workspace }} />}>
          The workspace's threads
        </ButtonLink>
      }
    >
      There's nothing at this address in {workspace}.
    </NotFound>
  );
}
