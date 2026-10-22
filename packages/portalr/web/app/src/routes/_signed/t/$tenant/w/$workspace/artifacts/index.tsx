import { EmptyState, PageHeader, Row, RowLink, Rows } from "@portalr/ui";
import { useQuery } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { titlesOf } from "../../../../../../../titles";
import { Uploader } from "../../../../../../../upload";
import { Connection, useWorkspace } from "../../../../../../../workspace";

/** The workspace's artifacts, as its log holds them: each by kind, and its latest version. */
export const Route = createFileRoute("/_signed/t/$tenant/w/$workspace/artifacts/")({
  head: ({ params, match }) => ({
    meta: [{ title: match.context.title(`Artifacts · ${params.workspace}`) }],
  }),
  // The titles are read before the page shows, so no id turns into a title as it opens. They are
  // only names: where they can't be read, the page shows ids, and reads them again on the page.
  // What the log later says changed an artifact makes them stale (`client`'s `stale`), and the
  // page reads them again.
  loader: async ({ context, params }) => {
    await context.queryClient
      .ensureQueryData(context.queries.artifactr.artifacts(params.tenant, params.workspace))
      .catch(() => undefined);
  },
  component: Artifacts,
});

function Artifacts() {
  const { tenant, workspace } = Route.useParams();
  const context = Route.useRouteContext();
  const { queries } = context;
  const snapshot = useWorkspace();
  // Titles are read from the artifacts' data, which the log doesn't carry; the loader has them.
  const { data: read } = useQuery(queries.artifactr.artifacts(tenant, workspace));
  const titles = titlesOf(read);
  const listed = Object.values(snapshot.state.artifacts)
    .filter((artifact) => !artifact.archived)
    .sort((a, b) => a.id.localeCompare(b.id));
  return (
    <>
      <PageHeader title="Artifacts" meta={`What the agent and people make in ${workspace}`} />
      <Connection snapshot={snapshot} waiting="the workspace" />
      <Uploader context={context} tenant={tenant} workspace={workspace} />
      {snapshot.status === "live" && listed.length === 0 && (
        <EmptyState title="No artifacts yet">
          An artifact appears here when the agent makes one in a thread, when someone accepts a
          proposal that creates one, or when someone uploads a file.
        </EmptyState>
      )}
      {listed.length > 0 && (
        <Rows label="Artifacts">
          {listed.map((artifact) => (
            <Row
              key={artifact.id}
              name={
                <RowLink
                  aria-describedby={`${artifact.id}-meta`}
                  render={
                    <Link
                      to="/t/$tenant/w/$workspace/artifacts/$artifact"
                      params={{ tenant, workspace, artifact: artifact.id }}
                    />
                  }
                >
                  {titles.has(artifact.id) ? (
                    titles.get(artifact.id)
                  ) : (
                    <span className="font-mono">{artifact.id}</span>
                  )}
                </RowLink>
              }
              meta={
                <span id={`${artifact.id}-meta`}>
                  {titles.has(artifact.id) && (
                    <>
                      <span className="font-mono">{artifact.id}</span>,{" "}
                    </>
                  )}
                  {artifact.kind}, version {artifact.version}
                </span>
              }
            />
          ))}
        </Rows>
      )}
    </>
  );
}
