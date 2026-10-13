import { changedAccess, type GrantrApi, orThrow, refusal } from "@portalr/client";
import { Button, Card, ConfirmDialog, ItemTable, SectionTitle, TextField } from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute, notFound } from "@tanstack/react-router";
import { useActionState, useMemo } from "react";
import { accessIn } from "../../../../../access";

type Member = GrantrApi.components["schemas"]["Member"];

/** A member's kind, as people read it. */
const KIND: Record<Member["kind"], string> = {
  user: "Person",
  service_principal: "Service principal",
};

/**
 * A tenant's members, people and service principals, for whoever may add one: invited by email,
 * or a service principal made by name, and each removed, where grantr allows, once confirmed.
 */
export const Route = createFileRoute("/_signed/t/$tenant/access/members")({
  loader: async ({ context, params }) => {
    const checks = accessIn(context.queries, params.tenant);
    const allowed = checks.select(await context.queryClient.ensureQueryData(checks));
    if (!allowed.has("grantr:add_member")) {
      throw notFound();
    }
    await context.queryClient.ensureQueryData(context.queries.grantr.members(params.tenant));
  },
  component: Members,
});

function Members() {
  const { tenant } = Route.useParams();
  const { queries, commands, queryClient } = Route.useRouteContext();
  const checks = useMemo(() => accessIn(queries, tenant), [queries, tenant]);
  const { data: allowed } = useSuspenseQuery(checks);
  const { data: members } = useSuspenseQuery(queries.grantr.members(tenant));
  const sorted = [...members].sort(
    (a, b) => a.kind.localeCompare(b.kind) || a.id.localeCompare(b.id),
  );
  const changed = <A,>(answer: Promise<A>) => changedAccess(queryClient, tenant, answer);

  const [invited, invite, inviting] = useActionState(
    async (_last: { said: string; refused: boolean } | null, form: FormData) => {
      const email = String(form.get("email"));
      const answer = await changed(commands.portalr.invite(tenant, email));
      return answer.outcome === "done"
        ? { said: `${email} is invited, as ${answer.result.user}.`, refused: false }
        : { said: refusal("Not invited", answer), refused: true };
    },
    null,
  );
  const [made, make, making] = useActionState(
    async (_last: { said: string; refused: boolean } | null, form: FormData) => {
      const id = String(form.get("principal"));
      const answer = await changed(
        commands.grantr.addMember(tenant, { kind: "service_principal", id }),
      );
      return answer.outcome === "done"
        ? { said: `${id} is a service principal of ${tenant}.`, refused: false }
        : { said: refusal("Not added", answer), refused: true };
    },
    null,
  );

  return (
    <div className="flex flex-col gap-6">
      <ItemTable
        caption="Members"
        columns={[
          { label: "Member", cell: (member) => member.id },
          { label: "Kind", cell: (member) => KIND[member.kind] },
        ]}
        items={sorted}
        keyOf={(member) => `${member.kind}:${member.id}`}
        {...(allowed.has("grantr:remove_member") && {
          actions: (member: Member) => (
            <ConfirmDialog
              label={`Remove ${member.id}`}
              title={`Remove ${member.id} from ${tenant}?`}
              confirm="Remove"
              onConfirm={async () =>
                orThrow("Not removed", await changed(commands.grantr.removeMember(tenant, member)))
              }
            >
              <p>
                {member.id} loses every role in {tenant}, its places in groups, and
                {member.kind === "service_principal" ? " every key issued to it" : " its keys"}.
              </p>
            </ConfirmDialog>
          ),
        })}
        empty="No members yet."
      />
      <div className="grid gap-4 md:grid-cols-2">
        <Card render={<section aria-labelledby="invite" />} className="flex flex-col gap-3">
          <SectionTitle id="invite">Invite someone</SectionTitle>
          <form className="flex flex-col gap-3" action={invite}>
            <TextField label="Email" name="email" type="email" autoComplete="off" required />
            {invited && <p role={invited.refused ? "alert" : "status"}>{invited.said}</p>}
            <Button type="submit" disabled={inviting} className="self-start">
              Invite
            </Button>
          </form>
        </Card>
        <Card render={<section aria-labelledby="principal" />} className="flex flex-col gap-3">
          <SectionTitle id="principal">Add a service principal</SectionTitle>
          <form className="flex flex-col gap-3" action={make}>
            <TextField label="Name" name="principal" autoComplete="off" required />
            {made && <p role={made.refused ? "alert" : "status"}>{made.said}</p>}
            <Button type="submit" disabled={making} className="self-start">
              Add
            </Button>
          </form>
        </Card>
      </div>
    </div>
  );
}
