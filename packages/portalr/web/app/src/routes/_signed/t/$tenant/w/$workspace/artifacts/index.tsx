import { EmptyState, PageHeader, Row, RowLink, Rows } from "@portalr/ui";
import { createFileRoute, Link } from "@tanstack/react-router";
import { Connection, useWorkspace } from "../../../../../../../workspace";

/** The workspace's artifacts, as its log holds them: each by kind, and its latest version. */
export const Route = createFileRoute("/_signed/t/$tenant/w/$workspace/artifacts/")({
  head: ({ params }) => ({ meta: [{ title: `Artifacts · ${params.workspace} · portalr` }] }),
  component: Artifacts,
});

function Artifacts() {
  const { tenant, workspace } = Route.useParams();
  const snapshot = useWorkspace();
  const listed = Object.values(snapshot.state.artifacts)
    .filter((artifact) => !artifact.archived)
    .sort((a, b) => a.id.localeCompare(b.id));
  return (
    <>
      <PageHeader title="Artifacts" meta={`What the agent and people make in ${workspace}`} />
      <Connection snapshot={snapshot} waiting="the workspace" />
      {snapshot.status === "live" && listed.length === 0 && (
        <EmptyState title="No artifacts yet">
          An artifact appears here when the agent makes one in a thread, or when someone accepts a
          proposal that creates one.
        </EmptyState>
      )}
      {listed.length > 0 && (
        <Rows label="Artifacts">
          {listed.map((artifact) => (
            <Row key={artifact.id}>
              <RowLink
                render={
                  <Link
                    to="/t/$tenant/w/$workspace/artifacts/$artifact"
                    params={{ tenant, workspace, artifact: artifact.id }}
                  />
                }
              >
                <span className="font-mono">{artifact.id}</span>
              </RowLink>
              <span className="text-muted">
                {artifact.kind}, version {artifact.version}
              </span>
            </Row>
          ))}
        </Rows>
      )}
    </>
  );
}
