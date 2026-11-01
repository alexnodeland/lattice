import {
  type Approval,
  answeredBy,
  answerersOf,
  askedBy,
  changedApprovals,
  confirmPage,
  peopleIn,
  Refused,
  refusal,
  usePeople,
} from "@portalr/client";
import {
  Alert,
  ApprovalDetails,
  ApprovalStanding,
  Breadcrumbs,
  Button,
  ButtonLink,
  CRUMB,
  NotFound as NotFoundPage,
  PageHeader,
  TextArea,
} from "@portalr/ui";
import { useQuery, useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute, Link, notFound } from "@tanstack/react-router";
import { useState } from "react";

/**
 * One approval as it stands, for one who may answer it or the person it was asked for (grantr
 * ADR-0040): what the call would do, who asked, and where it stands. One who may answer it, by
 * the store's rules, answers here, on the `portalr` surface, with a reason if they give one. A
 * confirmation of the reader's own `admin_high` call is answered on admin's confirm page alone,
 * which this page links to (lattice RFC-0014). Anyone else is told it isn't there.
 */
export const Route = createFileRoute("/_signed/t/$tenant/approvals/$approval")({
  head: ({ params, match }) => ({
    meta: [{ title: match.context.title(`Approval · ${params.tenant}`) }],
  }),
  loader: async ({ context, params }) => {
    try {
      return await context.queryClient.ensureQueryData(
        context.queries.grantr.approval(params.tenant, params.approval),
      );
    } catch (error) {
      if (error instanceof Refused && error.status === 404) {
        throw notFound();
      }
      throw error;
    }
  },
  notFoundComponent: NotFound,
  component: ApprovalPage,
});

function ApprovalPage() {
  const { tenant, approval: id } = Route.useParams();
  const { config, queries, user } = Route.useRouteContext();
  const { data: approval } = useSuspenseQuery(queries.grantr.approval(tenant, id));
  // Whether the reader may answer it is the store's to say: it is among those it lists for them.
  const { data: answerable } = useQuery(queries.grantr.approvals(tenant));
  const names = usePeople(queries, config.people, tenant, peopleIn(approval, user));
  const mayAnswer = answerable?.some((each) => each.id === id) ?? false;
  // Why an answer was refused stays when the page, read again, shows the approval settled.
  const [refused, setRefused] = useState<string | null>(null);
  return (
    <section aria-labelledby="approval" className="flex max-w-190 flex-col gap-6">
      <PageHeader
        id="approval"
        title={approval.rendering.title}
        breadcrumbs={
          <Breadcrumbs
            trail={[
              {
                label: "Approvals",
                render: (
                  <Link to="/t/$tenant/approvals" params={{ tenant }} activeOptions={CRUMB} />
                ),
              },
            ]}
          />
        }
        meta={<ApprovalStanding state={approval.state} />}
      />
      <ApprovalDetails
        approval={approval}
        askedBy={askedBy(approval, user, names)}
        answeredBy={
          approval.answer == null ? undefined : answeredBy(approval.answer.by, user, names)
        }
        answerers={answerersOf(approval, user, names)}
      />
      {approval.state === "pending" &&
        (approval.answerers.confirmation ? (
          <Confirmation approval={approval} mine={mayAnswer} />
        ) : mayAnswer ? (
          <Answer tenant={tenant} approval={approval} onRefused={setRefused} />
        ) : (
          <p>It waits for one of those who may answer it.</p>
        ))}
      {refused && <Alert tone="error">{refused}</Alert>}
    </section>
  );
}

/**
 * A confirmation, which no page but admin's confirm page answers: to the caller, a link there;
 * to anyone else, that it waits for them.
 */
function Confirmation({ approval, mine }: { approval: Approval; mine: boolean }) {
  return mine ? (
    <div className="flex flex-col items-start gap-3">
      <p>This is your own call, which only you confirm, on admin's confirm page.</p>
      <ButtonLink href={confirmPage(approval.id)}>Open the confirm page</ButtonLink>
    </div>
  ) : (
    <p>It waits for the person who called to confirm it.</p>
  );
}

/**
 * Approve or deny, once, with a reason if one is given. A refusal is handed to the page to say
 * why: one who answered first, or a deadline passed, settles it, and the page, read again, shows
 * that, without these buttons.
 */
function Answer({
  tenant,
  approval,
  onRefused,
}: {
  tenant: string;
  approval: Approval;
  onRefused: (why: string | null) => void;
}) {
  const { commands, queryClient } = Route.useRouteContext();
  const [reason, setReason] = useState("");
  const [sending, setSending] = useState<boolean | null>(null);
  async function answer(approved: boolean) {
    setSending(approved);
    onRefused(null);
    const answered = await changedApprovals(
      queryClient,
      tenant,
      commands.grantr.answerApproval(tenant, approval, { approved, reason }, "portalr"),
    );
    setSending(null);
    if (answered.outcome === "refused") {
      onRefused(refusal(approved ? "It wasn't approved" : "It wasn't denied", answered));
    }
  }
  return (
    <form
      aria-label="Your answer"
      className="flex flex-col gap-3"
      onSubmit={(event) => event.preventDefault()}
    >
      <TextArea
        label="Why"
        hint="Optional: whoever asked sees it."
        name="reason"
        rows={2}
        value={reason}
        onValueChange={(value) => setReason(String(value))}
      />
      <span className="flex gap-2">
        <Button
          disabled={sending !== null}
          pending={sending === true}
          onClick={() => void answer(true)}
        >
          Approve
        </Button>
        <Button
          variant="secondary"
          disabled={sending !== null}
          pending={sending === false}
          onClick={() => void answer(false)}
        >
          Deny
        </Button>
      </span>
    </form>
  );
}

function NotFound() {
  const { tenant } = Route.useParams();
  return (
    <NotFoundPage
      title="Approval not found"
      action={
        <ButtonLink render={<Link to="/t/$tenant/approvals" params={{ tenant }} />}>
          All approvals
        </ButtonLink>
      }
    >
      There's no approval here by that id, or it isn't one you may see.
    </NotFoundPage>
  );
}
