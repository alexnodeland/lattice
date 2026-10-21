import { allowedIn, changes, keys, Refused, thumbs, useMe, workspaceOf } from "@portalr/client";
import {
  AppHostContext,
  ArtifactContent,
  Card,
  FormHostContext,
  PageHeader,
  ProposalCard,
  proposedOn,
  Revisions,
  SectionTitle,
  Thumbs,
} from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute, Link, notFound } from "@tanstack/react-router";
import { useEffect, useMemo } from "react";
import { useAppHost } from "../../../../../../../app-host";
import { author } from "../../../../../../../author";
import { useFormHost } from "../../../../../../../form-host";
import { KillSwitch } from "../../../../../../../kill-switch";
import { NativeFile, TextChanges, wordsChanged } from "../../../../../../../native-file";
import { NativeProposal } from "../../../../../../../native-proposal";
import { NATIVE, RENDERERS } from "../../../../../../../renderers";
import { titleOf } from "../../../../../../../titles";
import { Connection, useStream, useWorkspace } from "../../../../../../../workspace";

/**
 * An artifact: its content, through its kind's renderer; its revisions, newest first, each with
 * who made it, when, and what it changed, readable (portalr ADR-0054); and the proposals open on
 * it. Its revisions are read over REST, again as the workspace's log moves past them.
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
  const context = Route.useRouteContext();
  const { queries, queryClient, user } = context;
  const me = useMe(queries, user, tenant);
  const checks = useMemo(
    () => allowedIn(queries, tenant, workspaceOf(workspace), ACTIONS),
    [queries, tenant, workspace],
  );
  const { data: allowed } = useSuspenseQuery(checks);
  const { data: revisions } = useSuspenseQuery(queries.artifactr.revisions(tenant, workspace, id));
  const stream = useStream();
  const snapshot = useWorkspace();
  const host = useFormHost({ queries, tenant, workspace, me, renderers: RENDERERS });
  const apps = useAppHost(context.config);
  const latest = useMemo(
    () =>
      revisions.reduce<(typeof revisions)[number] | undefined>(
        (newest, revision) => (newest && newest.version > revision.version ? newest : revision),
        undefined,
      ),
    [revisions],
  );
  // Each revision as the list names who made it: the reader as "You".
  const shown = useMemo(
    () =>
      revisions.map((revision) => ({
        version: revision.version,
        kind: revision.kind,
        data: revision.data,
        by: author(revision.actor, me),
        at: revision.at ?? null,
      })),
    [revisions, me],
  );
  const byVersion = useMemo(
    () => new Map(revisions.map((revision) => [revision.version, revision.data])),
    [revisions],
  );
  const logged = snapshot.state.artifacts[id]?.version;
  const read = latest?.version;
  useEffect(() => {
    if (logged !== undefined && read !== undefined && logged > read) {
      void queryClient.invalidateQueries({
        queryKey: keys.artifactr.revisions(tenant, workspace, id),
      });
    }
  }, [logged, read, queryClient, tenant, workspace, id]);
  if (latest === undefined) {
    return null; // the loader found it; it can't have no revisions
  }
  const title = titleOf(latest.kind, latest.data);
  const native = NATIVE.get(latest.kind);
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
        breadcrumbs={[
          {
            label: "Artifacts",
            render: <Link to="/t/$tenant/w/$workspace/artifacts" params={{ tenant, workspace }} />,
          },
        ]}
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
        <FormHostContext value={host}>
          <AppHostContext value={apps}>
            {latest.kind === "app" && (
              <KillSwitch queries={queries} tenant={tenant} workspace={workspace} />
            )}
            <ArtifactContent
              kind={latest.kind}
              data={latest.data}
              shown={{ id, version: latest.version, archived: latest.archived }}
              renderers={RENDERERS}
            />
          </AppHostContext>
        </FormHostContext>
      </Card>
      {native && (
        <NativeFile place={{ context, tenant, workspace, artifact: id }} native={native} me={me} />
      )}
      {open.length > 0 && (
        <section aria-labelledby="open" className="flex flex-col gap-3">
          <SectionTitle id="open">Open proposals</SectionTitle>
          {open.map((proposal) => {
            const onRespond = (decision: "accept" | "reject") =>
              stream.send({ type: "respond_to_proposal", proposal_id: proposal.id, decision });
            return native ? (
              <NativeProposal
                key={proposal.id}
                place={{ context, tenant, workspace, artifact: id }}
                native={native}
                me={me}
                proposal={proposal}
                onRespond={onRespond}
              />
            ) : (
              <ProposalCard key={proposal.id} proposal={proposal} onRespond={onRespond} />
            );
          })}
        </section>
      )}
      <section aria-labelledby="revisions" className="flex flex-col gap-3">
        <SectionTitle id="revisions">Revisions</SectionTitle>
        {/* An app's revision runs in its preview, one at a time, as the page's apps do. */}
        <AppHostContext value={apps}>
          <Revisions
            id={id}
            revisions={shown}
            renderers={RENDERERS}
            compare={changes}
            archived={latest.archived}
            more={(revision, before) => {
              const was = before === null ? undefined : byVersion.get(before);
              // A native file's words are compared apart, from the text the app read from each.
              return (
                NATIVE.has(revision.kind) &&
                before !== null &&
                was !== undefined &&
                wordsChanged(was, revision.data) && (
                  <TextChanges
                    queries={queries}
                    tenant={tenant}
                    workspace={workspace}
                    artifact={id}
                    versions={[before, revision.version]}
                  />
                )
              );
            }}
          />
        </AppHostContext>
      </section>
    </section>
  );
}
