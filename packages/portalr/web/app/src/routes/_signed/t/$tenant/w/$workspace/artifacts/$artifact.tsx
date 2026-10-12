import { changes, keys, Refused, thumbs } from "@portalr/client";
import { ArtifactContent, Diff, ProposalCard, proposedOn, rendererFor, Thumbs } from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute, notFound } from "@tanstack/react-router";
import { useEffect, useMemo } from "react";
import { allowedIn } from "../../../../../../../allowed";
import { useMe } from "../../../../../../../me";
import { RENDERERS } from "../../../../../../../renderers";
import { Connection, useStream, useWorkspace } from "../../../../../../../workspace";

/**
 * An artifact: its content, through its kind's renderer; its revisions, newest first, each with
 * what it changed; and the proposals open on it. Its revisions are read over REST, again as the
 * workspace's log moves past them.
 */
/** What a person may do on an artifact's page, beyond responding to its proposals. */
const ACTIONS = ["artifactr:give_feedback"] as const;

export const Route = createFileRoute("/_signed/t/$tenant/w/$workspace/artifacts/$artifact")({
  head: ({ params }) => ({
    meta: [{ title: `${params.artifact} · ${params.workspace} · portalr` }],
  }),
  loader: async ({ context, params }) => {
    const { tenant, workspace, artifact } = params;
    await Promise.all([
      context.queryClient.ensureQueryData(allowedIn(context.queries, tenant, workspace, ACTIONS)),
      context.queryClient.ensureQueryData(context.queries.grantr.memberships(context.user)),
    ]);
    try {
      const revisions = await context.queryClient.ensureQueryData(
        context.queries.artifactr.revisions(tenant, workspace, artifact),
      );
      if (revisions.length === 0) {
        throw notFound();
      }
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
  const { queries, queryClient, user } = Route.useRouteContext();
  const me = useMe(queries, user, tenant);
  const { data: allowed } = useSuspenseQuery(allowedIn(queries, tenant, workspace, ACTIONS));
  const { data: revisions } = useSuspenseQuery(queries.artifactr.revisions(tenant, workspace, id));
  const stream = useStream();
  const snapshot = useWorkspace();
  // The revisions in order, whatever order the server sent, each with what it changed: worked out
  // once each time they are read, not on every event the workspace's stream brings.
  const history = useMemo(() => {
    const ordered = [...revisions].sort((a, b) => a.version - b.version);
    const latest = ordered.at(-1);
    if (latest === undefined) {
      return null;
    }
    const renderer = rendererFor(latest.kind, RENDERERS);
    const versions = ordered.map((revision, index) => {
      const before = ordered[index - 1];
      const was = before ? renderer.text(before.data) : "";
      return { revision, changes: changes(was, renderer.text(revision.data), renderer.diff) };
    });
    return { latest, versions: versions.reverse() };
  }, [revisions]);
  const logged = snapshot.state.artifacts[id]?.version;
  const read = history?.latest.version;
  useEffect(() => {
    if (logged !== undefined && read !== undefined && logged > read) {
      void queryClient.invalidateQueries({
        queryKey: keys.artifactr.revisions(tenant, workspace, id),
      });
    }
  }, [logged, read, queryClient, tenant, workspace, id]);
  if (history === null) {
    return null; // the loader found it; it can't have no revisions
  }
  const { latest, versions } = history;
  const open = Object.values(snapshot.state.proposals).filter(
    (proposal) => proposal.status === "open" && proposedOn(proposal) === id,
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
        {allowed.has("artifactr:give_feedback") && (
          <Thumbs
            given={thumbs(snapshot.state.artifacts[id]?.feedback ?? [], me)}
            onThumbs={(up, comment) =>
              stream.send({
                type: "give_feedback",
                feedback_type: "thumbs",
                target: { kind: "artifact", artifact_id: id, version: latest.version },
                value: comment === null ? { up } : { up, comment },
              })
            }
          />
        )}
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
          {versions.map(({ revision, changes }) => (
            <li
              key={revision.version}
              aria-label={`Version ${revision.version}`}
              className="flex flex-col gap-1"
            >
              <span className="font-semibold text-sm">Version {revision.version}</span>
              <Diff changes={changes} />
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
