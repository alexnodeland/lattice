import { allowedIn, changes, keys, Refused, thumbs, useMe, workspaceOf } from "@portalr/client";
import {
  ArtifactContent,
  Card,
  Diff,
  PageHeader,
  ProposalCard,
  proposedOn,
  rendererFor,
  SectionTitle,
  TextLink,
  Thumbs,
} from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute, Link, notFound } from "@tanstack/react-router";
import { useEffect, useMemo } from "react";
import { RENDERERS } from "../../../../../../../renderers";
import { titleOf } from "../../../../../../../titles";
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
    await context.queryClient.ensureQueryData(
      allowedIn(context.queries, tenant, workspaceOf(workspace), ACTIONS),
    );
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
    <>
      <PageHeader title="Artifact not found" />
      <p>There's no artifact here by that name, or it isn't one you can see.</p>
    </>
  ),
  component: Artifact,
});

function Artifact() {
  const { tenant, workspace, artifact: id } = Route.useParams();
  const { queries, queryClient, user } = Route.useRouteContext();
  const me = useMe(queries, user, tenant);
  const checks = useMemo(
    () => allowedIn(queries, tenant, workspaceOf(workspace), ACTIONS),
    [queries, tenant, workspace],
  );
  const { data: allowed } = useSuspenseQuery(checks);
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
  const title = titleOf(latest.kind, latest.data);
  const open = Object.values(snapshot.state.proposals).filter(
    (proposal) => proposal.status === "open" && proposedOn(proposal) === id,
  );
  const feedback = allowed.has("artifactr:give_feedback") && (
    <Thumbs
      given={thumbs(
        (snapshot.state.artifacts[id]?.feedback ?? []).filter(
          (given) => given.version === latest.version,
        ),
        me,
      )}
      onThumbs={(up, comment) =>
        stream.send({
          type: "give_feedback",
          feedback_type: "thumbs",
          target: { kind: "artifact", artifact_id: id, version: latest.version },
          value: comment === null ? { up } : { up, comment },
        })
      }
    />
  );
  return (
    <section aria-labelledby="artifact" className="flex max-w-190 flex-col gap-6">
      <PageHeader
        id="artifact"
        title={title ?? id}
        mono={title === null}
        crumb={
          <TextLink
            render={<Link to="/t/$tenant/w/$workspace/artifacts" params={{ tenant, workspace }} />}
          >
            Artifacts
          </TextLink>
        }
        meta={[
          title === null ? null : id,
          latest.kind,
          `version ${latest.version}`,
          latest.archived ? "archived" : null,
        ]
          .filter(Boolean)
          .join(", ")}
        actions={feedback}
      />
      <Connection snapshot={snapshot} waiting="the workspace" />
      <Card>
        <ArtifactContent kind={latest.kind} data={latest.data} renderers={RENDERERS} />
      </Card>
      {open.length > 0 && (
        <section aria-labelledby="open" className="flex flex-col gap-3">
          <SectionTitle id="open">Open proposals</SectionTitle>
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
      <section aria-labelledby="revisions" className="flex flex-col gap-3">
        <SectionTitle id="revisions">Revisions</SectionTitle>
        <ol aria-label="Revisions" className="flex flex-col gap-3">
          {versions.map(({ revision, changes }) => (
            <li
              key={revision.version}
              aria-label={`Version ${revision.version}`}
              className="flex flex-col gap-2 rounded-lg border border-line bg-surface p-4"
            >
              <span className="font-semibold text-sm">Version {revision.version}</span>
              <Diff changes={changes} />
            </li>
          ))}
        </ol>
      </section>
    </section>
  );
}
