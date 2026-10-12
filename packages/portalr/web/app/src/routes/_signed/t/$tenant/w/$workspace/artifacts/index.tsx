import { TextLink } from "@portalr/ui";
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
    <section aria-labelledby="artifacts" className="flex flex-col gap-4">
      <h2 id="artifacts" className="font-semibold text-lg">
        Artifacts
      </h2>
      <Connection snapshot={snapshot} waiting="the workspace" />
      {snapshot.status === "live" && listed.length === 0 && <p>No artifacts yet.</p>}
      {listed.length > 0 && (
        <ul aria-label="Artifacts" className="flex flex-col gap-2">
          {listed.map((artifact) => (
            <li key={artifact.id} className="flex gap-2">
              <TextLink
                render={
                  <Link
                    to="/t/$tenant/w/$workspace/artifacts/$artifact"
                    params={{ tenant, workspace, artifact: artifact.id }}
                  />
                }
              >
                {artifact.id}
              </TextLink>
              <span className="text-muted">
                {artifact.kind}, version {artifact.version}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
