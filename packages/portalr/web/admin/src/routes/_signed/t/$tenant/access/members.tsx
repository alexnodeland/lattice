import { type GrantrApi, type Names, orThrow, refusal } from "@portalr/client";
import { Alert, Button, ConfirmDialog, ItemTable, TextField } from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useActionState, useState } from "react";
import {
  byKindThenName,
  KIND,
  opening,
  peopleIn,
  type Said,
  useAccess,
  useNames,
} from "../../../../../access";
import { Folded, Toolbar } from "../../../../../folded";

type Member = GrantrApi.components["schemas"]["Member"];

/**
 * A tenant's members, people first, then service principals, for whoever may add one: invited by
 * email, or a service principal made by name, and each removed, where grantr allows, once
 * confirmed. No one is offered their own removal.
 */
export const Route = createFileRoute("/_signed/t/$tenant/access/members")({
  head: ({ params, match }) => ({
    meta: [{ title: match.context.title(`Members · ${params.tenant}`) }],
  }),
  beforeLoad: ({ context, params }) => opening(context, params.tenant, "grantr:add_member"),
  loader: ({ context, params }) =>
    context.queryClient.ensureQueryData(context.queries.grantr.members(params.tenant)),
  component: Members,
});

function Members() {
  const { tenant } = Route.useParams();
  const { queries, commands, user } = Route.useRouteContext();
  const { allowed, changed } = useAccess(tenant);
  const { data: members } = useSuspenseQuery(queries.grantr.members(tenant));
  const yourself = (member: Member) => member.kind === "user" && member.id === user;
  const names = useNames(tenant, peopleIn(members));
  const removes = allowed.has("grantr:remove_member");

  const [email, setEmail] = useState("");
  const [invited, invite, inviting] = useActionState(async (_last: Said) => {
    const answer = await changed(commands.portalr.invite(tenant, email));
    if (answer.outcome === "refused") {
      return { said: refusal("Not invited", answer), refused: true };
    }
    setEmail("");
    return { said: `${email} is invited.`, refused: false };
  }, null);
  const [made, make, making] = useActionState(async (_last: Said, form: FormData) => {
    const id = String(form.get("principal"));
    const answer = await changed(
      commands.grantr.addMember(tenant, { kind: "service_principal", id }),
    );
    return answer.outcome === "done"
      ? { said: `${id} is a service principal of ${tenant}.`, refused: false }
      : { said: refusal("Not added", answer), refused: true };
  }, null);

  return (
    <div className="flex flex-col gap-4">
      <Toolbar>
        <Folded title="Invite someone" action="Invite…" primary>
          <form className="flex flex-col gap-3" action={invite}>
            <TextField
              label="Email"
              name="email"
              type="email"
              autoComplete="off"
              required
              value={email}
              onValueChange={(value) => setEmail(String(value))}
            />
            {invited && <Alert tone={invited.refused ? "error" : "info"}>{invited.said}</Alert>}
            <Button type="submit" disabled={inviting} className="self-start">
              Invite
            </Button>
          </form>
        </Folded>
        <Folded title="Add a service principal" action="Add…">
          <form className="flex flex-col gap-3" action={make}>
            <TextField label="Name" name="principal" autoComplete="off" required />
            {made && <Alert tone={made.refused ? "error" : "info"}>{made.said}</Alert>}
            <Button type="submit" disabled={making} className="self-start">
              Add
            </Button>
          </form>
        </Folded>
      </Toolbar>
      <ItemTable
        caption="Members"
        columns={[
          {
            key: "member",
            label: "Member",
            cell: (member) =>
              member.kind === "user" ? (
                // The reader is "You"; anyone else their email where the deployment names
                // people, their id cut short where it doesn't, whole on hover.
                <span title={member.id}>{yourself(member) ? "You" : names(member.id)}</span>
              ) : (
                member.id
              ),
          },
          {
            key: "kind",
            label: "Kind",
            cell: (member) => <span className="first-letter:uppercase">{KIND[member.kind]}</span>,
          },
        ]}
        items={[...members].sort(byKindThenName(names))}
        keyOf={(member) => `${member.kind}:${member.id}`}
        actions={
          removes
            ? (member) =>
                yourself(member) ? null : <Remove tenant={tenant} member={member} names={names} />
            : undefined
        }
        empty={{ title: "No members yet", body: "Invite someone, or add a service principal." }}
      />
    </div>
  );
}

/** A member removed, once confirmed: what goes with them, which keys only a principal has. */
function Remove({ tenant, member, names }: { tenant: string; member: Member; names: Names }) {
  const { commands } = Route.useRouteContext();
  const { changed } = useAccess(tenant);
  const name = member.kind === "user" ? names(member.id) : member.id;
  return (
    <ConfirmDialog
      label="Remove"
      about={name}
      look="danger-soft"
      size="sm"
      title={`Remove ${name} from ${tenant}?`}
      confirm="Remove"
      onConfirm={async () =>
        orThrow("Not removed", await changed(commands.grantr.removeMember(tenant, member)))
      }
    >
      <p>
        {member.kind === "user"
          ? `${name} loses every role in ${tenant}, and their places in groups.`
          : `${name} loses every role in ${tenant}, its places in groups, and every key issued to it.`}
      </p>
    </ConfirmDialog>
  );
}
