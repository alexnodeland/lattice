import {
  type Approval,
  answeredBy,
  approvalPage,
  askedBy,
  askedFor,
  changedApprovals,
  peopleIn,
  Refused,
  refusal,
  usePeople,
} from "@portalr/client";
import {
  Account,
  Alert,
  ApprovalDetails,
  ApprovalStanding,
  Button,
  ButtonLink,
  Plain,
  TextField,
} from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute, Link, notFound } from "@tanstack/react-router";
import { type FormEvent, useState } from "react";

/**
 * The confirm page (lattice RFC-0014, ADR-0038): where the person who made an `admin_high` call
 * confirms they meant it, signed in, on the `portalr:confirm` surface, the only one that answers
 * a confirmation. Its address names the approval alone, as a client or a push links to it; the
 * approval's tenant is the one of the person's tenants that shows it. Each opening reads it
 * afresh, and the person types the tenant's name, which every `admin_high` action acts on,
 * before Confirm does anything.
 */
export const Route = createFileRoute("/_signed/confirm/$approval")({
  loader: async ({ context, params }) => {
    const { queries, queryClient, user } = context;
    const memberships = await queryClient.ensureQueryData(queries.grantr.memberships(user));
    for (const tenant of [...new Set(memberships.map((membership) => membership.tenant))].sort()) {
      try {
        // Read afresh, never from the cache: what is confirmed is the approval as it stands.
        await queryClient.fetchQuery({
          ...queries.grantr.approval(tenant, params.approval),
          staleTime: 0,
        });
        return { tenant };
      } catch (error) {
        // Not in this tenant, or not the person's to see: another of their tenants may show it.
        if (!(error instanceof Refused && (error.status === 403 || error.status === 404))) {
          throw error;
        }
      }
    }
    throw notFound();
  },
  // After the loader, so its answer's type is known to the match the title reads.
  head: ({ match }) => ({
    meta: [{ title: match.context.title("Confirm") }],
  }),
  notFoundComponent: NotFound,
  component: Confirm,
});

function Confirm() {
  const { tenant } = Route.useLoaderData();
  const { approval: id } = Route.useParams();
  const { config, queries, signed, user } = Route.useRouteContext();
  const { data: approval } = useSuspenseQuery(queries.grantr.approval(tenant, id));
  const names = usePeople(queries, config.people, tenant, peopleIn(approval, user));
  const [refused, setRefused] = useState<string | null>(null);
  const mine = approval.answerers.confirmation && askedFor(approval) === user;
  return (
    <Plain
      ui="admin"
      home={<Link to="/" />}
      title={`Confirm: ${approval.rendering.title}`}
      account={<Account signed={signed} />}
    >
      <div className="flex flex-col gap-6">
        <p className="flex flex-wrap items-center gap-2">
          <ApprovalStanding state={approval.state} />
          {`In ${tenant}, asked by ${askedBy(approval, user, names)}.`}
        </p>
        <ApprovalDetails
          approval={approval}
          askedBy={askedBy(approval, user, names)}
          answeredBy={
            approval.answer == null ? undefined : answeredBy(approval.answer.by, user, names)
          }
        />
        {!approval.answerers.confirmation ? (
          <div className="flex flex-col items-start gap-3">
            <p>This isn't a confirmation: those who may answer it do on its page.</p>
            <ButtonLink href={approvalPage(tenant, id)}>Open its page</ButtonLink>
          </div>
        ) : approval.state !== "pending" ? null : mine ? (
          <Confirming tenant={tenant} approval={approval} onRefused={setRefused} />
        ) : (
          <p>Only the person who made the call confirms it.</p>
        )}
        {refused && <Alert tone="error">{refused}</Alert>}
      </div>
    </Plain>
  );
}

/**
 * Confirm, once the tenant's name is typed, or cancel. Either is the caller's answer on the
 * confirm page; a refusal is handed to the page to say why, as the approval, read again, shows
 * it settled.
 */
function Confirming({
  tenant,
  approval,
  onRefused,
}: {
  tenant: string;
  approval: Approval;
  onRefused: (why: string | null) => void;
}) {
  const { commands, queryClient } = Route.useRouteContext();
  const [typed, setTyped] = useState("");
  const [sending, setSending] = useState<boolean | null>(null);
  async function answer(approved: boolean) {
    setSending(approved);
    onRefused(null);
    const answered = await changedApprovals(
      queryClient,
      tenant,
      commands.grantr.answerApproval(tenant, approval, { approved }, "portalr:confirm"),
    );
    setSending(null);
    if (answered.outcome === "refused") {
      onRefused(refusal(approved ? "It wasn't confirmed" : "It wasn't cancelled", answered));
    }
  }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (typed === tenant) {
      void answer(true);
    }
  }
  return (
    <form aria-label="Your confirmation" className="flex flex-col gap-3" onSubmit={submit}>
      <p>Confirm it only if you made this call and meant it. Nothing is done until you do.</p>
      <TextField
        label={`Type ${tenant} to confirm`}
        name="tenant"
        autoComplete="off"
        spellCheck={false}
        value={typed}
        onValueChange={(value) => setTyped(String(value))}
      />
      <span className="flex gap-2">
        <Button
          type="submit"
          disabled={typed !== tenant || sending !== null}
          pending={sending === true}
        >
          Confirm
        </Button>
        <Button
          variant="secondary"
          disabled={sending !== null}
          pending={sending === false}
          onClick={() => void answer(false)}
        >
          Cancel it
        </Button>
      </span>
    </form>
  );
}

function NotFound() {
  const { signed } = Route.useRouteContext();
  return (
    <Plain
      ui="admin"
      home={<Link to="/" />}
      title="Nothing to confirm"
      account={<Account signed={signed} />}
    >
      <p>There's no confirmation here by that id, or it isn't yours.</p>
      <ButtonLink render={<Link to="/" />}>Go to admin</ButtonLink>
    </Plain>
  );
}
