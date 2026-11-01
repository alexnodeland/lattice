import { askedBy, confirmPage, peopleIn, usePeople } from "@portalr/client";
import { Ago, EmptyState, PageHeader, Row, RowLink, Rows } from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";

/**
 * The approvals waiting in the tenant that the reader may answer, oldest first, from every
 * workspace (grantr ADR-0040): each a row with what is asked, who asked, where and when. A row
 * opens the approval's page; a confirmation of the reader's own `admin_high` call opens admin's
 * confirm page instead, the only page that answers it (lattice RFC-0014).
 */
export const Route = createFileRoute("/_signed/t/$tenant/approvals/")({
  head: ({ params, match }) => ({
    meta: [{ title: match.context.title(`Approvals · ${params.tenant}`) }],
  }),
  loader: ({ context, params }) =>
    context.queryClient.ensureQueryData(context.queries.grantr.approvals(params.tenant)),
  component: Waiting,
});

function Waiting() {
  const { tenant } = Route.useParams();
  const { config, queries, user } = Route.useRouteContext();
  const { data: approvals } = useSuspenseQuery(queries.grantr.approvals(tenant));
  const names = usePeople(
    queries,
    config.people,
    tenant,
    approvals.flatMap((approval) => peopleIn(approval, user)),
  );
  return (
    <section aria-labelledby="approvals" className="flex max-w-190 flex-col gap-6">
      <PageHeader id="approvals" title="Approvals" />
      {approvals.length === 0 ? (
        <EmptyState title="Nothing waits for you">
          A call that needs a person's yes waits here for those who may give it, until it is
          answered or expires.
        </EmptyState>
      ) : (
        <Rows label="Approvals waiting for you">
          {approvals.map((approval) => (
            <Row
              key={approval.id}
              name={
                approval.answerers.confirmation ? (
                  <RowLink href={confirmPage(approval.id)}>{approval.rendering.title}</RowLink>
                ) : (
                  <RowLink
                    render={
                      <Link
                        to="/t/$tenant/approvals/$approval"
                        params={{ tenant, approval: approval.id }}
                      />
                    }
                  >
                    {approval.rendering.title}
                  </RowLink>
                )
              }
              meta={
                <>
                  {`Asked by ${askedBy(approval, user, names)} in ${approval.scope.workspace_id}, `}
                  <Ago at={approval.asked_at} />
                  {approval.answerers.confirmation ? ". Yours to confirm, in admin." : ""}
                </>
              }
            />
          ))}
        </Rows>
      )}
    </section>
  );
}
