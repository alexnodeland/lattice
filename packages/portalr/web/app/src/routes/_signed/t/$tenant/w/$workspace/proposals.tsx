import type { Artifactr } from "@portalr/client";
import { ProposalCard, TextLink } from "@portalr/ui";
import { createFileRoute, Link } from "@tanstack/react-router";
import { Connection, useStream, useWorkspace } from "../../../../../../workspace";

/** Every proposal in the workspace, the open ones first, each with the artifact it would change. */
export const Route = createFileRoute("/_signed/t/$tenant/w/$workspace/proposals")({
  head: ({ params }) => ({ meta: [{ title: `Proposals · ${params.workspace} · portalr` }] }),
  component: Proposals,
});

/** The artifact a proposal would change, if it names one: a new one's is chosen on accepting. */
function changing(proposal: Artifactr.Proposal): string | null {
  const change = proposal.change;
  return change !== null && "artifact_id" in change ? (change.artifact_id ?? null) : null;
}

function Proposals() {
  const { tenant, workspace } = Route.useParams();
  const stream = useStream();
  const snapshot = useWorkspace();
  const listed = Object.values(snapshot.state.proposals).sort(
    (a, b) => Number(b.status === "open") - Number(a.status === "open"),
  );
  return (
    <section aria-labelledby="proposals" className="flex flex-col gap-4">
      <h2 id="proposals" className="font-semibold text-lg">
        Proposals
      </h2>
      <Connection snapshot={snapshot} waiting="the workspace" />
      {snapshot.status === "live" && listed.length === 0 && <p>No proposals yet.</p>}
      {listed.map((proposal) => {
        const artifact = changing(proposal);
        return (
          <ProposalCard
            key={proposal.id}
            proposal={proposal}
            onRespond={(decision) =>
              stream.send({ type: "respond_to_proposal", proposal_id: proposal.id, decision })
            }
          >
            {artifact && (
              <TextLink
                render={
                  <Link
                    to="/t/$tenant/w/$workspace/artifacts/$artifact"
                    params={{ tenant, workspace, artifact }}
                  />
                }
              >
                {artifact}
              </TextLink>
            )}
          </ProposalCard>
        );
      })}
    </section>
  );
}
