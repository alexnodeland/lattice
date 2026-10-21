import { useMe } from "@portalr/client";
import { EmptyState, PageHeader, ProposalCard, proposedOn, TextLink } from "@portalr/ui";
import { createFileRoute, Link } from "@tanstack/react-router";
import { NativeProposal } from "../../../../../../native-proposal";
import { NATIVE } from "../../../../../../renderers";
import { Connection, useStream, useWorkspace } from "../../../../../../workspace";

/**
 * Every proposal in the workspace, the open ones first, each with the artifact it would change; a
 * native file's with how it was made, whether it is outdated, and its pages and words beside the
 * head's (portalr ADR-0050).
 */
export const Route = createFileRoute("/_signed/t/$tenant/w/$workspace/proposals")({
  head: ({ params, match }) => ({
    meta: [{ title: match.context.title(`Proposals · ${params.workspace}`) }],
  }),
  component: Proposals,
});

function Proposals() {
  const { tenant, workspace } = Route.useParams();
  const context = Route.useRouteContext();
  const me = useMe(context.queries, context.user, tenant);
  const stream = useStream();
  const snapshot = useWorkspace();
  const listed = Object.values(snapshot.state.proposals).sort(
    (a, b) => Number(b.status === "open") - Number(a.status === "open"),
  );
  return (
    <section aria-labelledby="proposals" className="flex max-w-190 flex-col gap-6">
      <PageHeader
        id="proposals"
        title="Proposals"
        meta={`Every proposal in ${workspace}, the open ones first`}
      />
      <Connection snapshot={snapshot} waiting="the workspace" />
      {snapshot.status === "live" && listed.length === 0 && (
        <EmptyState title="No proposals yet">
          The agent proposes a change to an artifact here when it may not make the change itself.
        </EmptyState>
      )}
      <div className="flex flex-col gap-3">
        {listed.map((proposal) => {
          const artifact = proposedOn(proposal);
          const native = artifact && NATIVE.get(snapshot.state.artifacts[artifact]?.kind ?? "");
          const onRespond = (decision: "accept" | "reject") =>
            stream.send({ type: "respond_to_proposal", proposal_id: proposal.id, decision });
          const link = artifact && (
            <TextLink
              variant="subtle"
              render={
                <Link
                  to="/t/$tenant/w/$workspace/artifacts/$artifact"
                  params={{ tenant, workspace, artifact }}
                />
              }
            >
              {artifact}
            </TextLink>
          );
          return artifact && native ? (
            <NativeProposal
              key={proposal.id}
              place={{ context, tenant, workspace, artifact }}
              native={native}
              me={me}
              proposal={proposal}
              onRespond={onRespond}
            >
              {link}
            </NativeProposal>
          ) : (
            <ProposalCard key={proposal.id} proposal={proposal} onRespond={onRespond}>
              {link}
            </ProposalCard>
          );
        })}
      </div>
    </section>
  );
}
