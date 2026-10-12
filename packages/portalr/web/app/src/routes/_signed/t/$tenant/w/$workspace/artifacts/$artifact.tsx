import { changes, keys, Refused } from "@portalr/client";
import { ArtifactContent, Diff, ProposalCard, rendererFor } from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute, notFound } from "@tanstack/react-router";
import { useEffect } from "react";
import { RENDERERS } from "../../../../../../../renderers";
import { Connection, useStream, useWorkspace } from "../../../../../../../workspace";

/**
 * An artifact: its content, through its kind's renderer; its revisions, newest first, each with
 * what it changed; and the proposals open on it. Its revisions are read over REST, again as the
 * workspace's log moves past them.
 */
export const Route = createFileRoute("/_signed/t/$tenant/w/$workspace/artifacts/$artifact")({
  head: ({ params }) => ({
    meta: [{ title: `${params.artifact} · ${params.workspace} · portalr` }],
  }),
  loader: async ({ context, params }) => {
    const { tenant, workspace, artifact } = params;
    try {
      await context.queryClient.ensureQueryData(
        context.queries.artifactr.revisions(tenant, workspace, artifact),
      );
    } catch (error) {
      if (error instanceof Refused && error.status === 404) {
        throw notFound();
      }
      throw error;
    }
  },
  notFoundComponent: () => (
    <section aria-labelledby="artifact">
      <h2 id="artifact" className="font-semibold text-lg">
        Artifact not found
      </h2>
      <p>There's no artifact here by that name, or it isn't one you can see.</p>
    </section>
  ),
  component: Artifact,
});

function Artifact() {
  const { tenant, workspace, artifact: id } = Route.useParams();
  const { queries, queryClient } = Route.useRouteContext();
  const { data: revisions } = useSuspenseQuery(queries.artifactr.revisions(tenant, workspace, id));
  const stream = useStream();
  const snapshot = useWorkspace();
  const logged = snapshot.state.artifacts[id]?.version;
  const latest = revisions.at(-1);
  useEffect(() => {
    if (logged !== undefined && latest !== undefined && logged > latest.version) {
      void queryClient.invalidateQueries({
        queryKey: keys.artifactr.revisions(tenant, workspace, id),
      });
    }
  }, [logged, latest, queryClient, tenant, workspace, id]);
  if (latest === undefined) {
    return null;
  }
  const renderer = rendererFor(latest.kind, RENDERERS);
  const open = Object.values(snapshot.state.proposals).filter(
    (proposal) =>
      proposal.status === "open" &&
      proposal.change !== null &&
      "artifact_id" in proposal.change &&
      proposal.change.artifact_id === id,
  );
  return (
    <div className="flex flex-col gap-6">
      <section aria-labelledby="artifact" className="flex flex-col gap-2">
        <h2 id="artifact" className="font-semibold text-lg">
          {id}
        </h2>
        <p className="text-muted text-sm">
          {latest.kind}, version {latest.version}
          {latest.archived && ", archived"}
        </p>
        <Connection snapshot={snapshot} waiting="the workspace" />
        <ArtifactContent kind={latest.kind} data={latest.data} renderers={RENDERERS} />
      </section>
      {open.length > 0 && (
        <section aria-labelledby="open" className="flex flex-col gap-2">
          <h3 id="open" className="font-semibold">
            Open proposals
          </h3>
          {open.map((proposal) => (
            <ProposalCard
              key={proposal.id}
              proposal={proposal}
              onRespond={(decision) =>
                stream.send({ type: "respond_to_proposal", proposal_id: proposal.id, decision })
              }
            />
          ))}
        </section>
      )}
      <section aria-labelledby="revisions" className="flex flex-col gap-2">
        <h3 id="revisions" className="font-semibold">
          Revisions
        </h3>
        <ol aria-label="Revisions" className="flex flex-col gap-3">
          {revisions
            .map((revision, index) => ({ revision, before: revisions[index - 1] }))
            .reverse()
            .map(({ revision, before }) => (
              <li
                key={revision.version}
                aria-label={`Version ${revision.version}`}
                className="flex flex-col gap-1"
              >
                <span className="font-semibold text-sm">Version {revision.version}</span>
                <Diff
                  changes={changes(
                    before ? renderer.text(before.data) : "",
                    renderer.text(revision.data),
                    renderer.diff,
                  )}
                />
              </li>
            ))}
        </ol>
      </section>
    </div>
  );
}
