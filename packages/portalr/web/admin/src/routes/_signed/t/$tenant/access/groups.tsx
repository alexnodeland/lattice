import { changedAccess, type GrantrApi, orThrow, refusal } from "@portalr/client";
import { Button, Card, ConfirmDialog, ItemTable, SectionTitle, TextField } from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute, notFound } from "@tanstack/react-router";
import { useActionState, useMemo } from "react";
import { accessIn } from "../../../../../access";

type Member = GrantrApi.components["schemas"]["Member"];

/** A member as a group's form names it: its kind and id, which grantr keeps apart. */
const named = (member: Member) => `${member.kind}:${member.id}`;

/**
 * A tenant's groups, each with its members, for whoever may manage them: a group created, or its
 * members replaced, from the tenant's members, and a group deleted, with its grants, once
 * confirmed. Choosing members needs reading them, which adding a member allows.
 */
export const Route = createFileRoute("/_signed/t/$tenant/access/groups")({
  loader: async ({ context, params }) => {
    const { queries, queryClient } = context;
    const checks = accessIn(queries, params.tenant);
    const allowed = checks.select(await queryClient.ensureQueryData(checks));
    if (!allowed.has("grantr:manage_groups")) {
      throw notFound();
    }
    await Promise.all([
      queryClient.ensureQueryData(queries.grantr.groups(params.tenant)),
      allowed.has("grantr:add_member") &&
        queryClient.ensureQueryData(queries.grantr.members(params.tenant)),
    ]);
  },
  component: Groups,
});

function Groups() {
  const { tenant } = Route.useParams();
  const { queries, commands, queryClient } = Route.useRouteContext();
  const checks = useMemo(() => accessIn(queries, tenant), [queries, tenant]);
  const { data: allowed } = useSuspenseQuery(checks);
  const { data: groups } = useSuspenseQuery(queries.grantr.groups(tenant));
  const changed = <A,>(answer: Promise<A>) => changedAccess(queryClient, tenant, answer);
  const listed = Object.entries(groups)
    .map(([name, members]) => ({ name, members }))
    .sort((a, b) => a.name.localeCompare(b.name));

  return (
    <div className="flex flex-col gap-6">
      <ItemTable
        caption="Groups"
        columns={[
          { label: "Group", cell: (group) => group.name },
          {
            label: "Members",
            cell: (group) => group.members.map((member) => member.id).join(", ") || "None",
          },
        ]}
        items={listed}
        keyOf={(group) => group.name}
        actions={(group) => (
          <ConfirmDialog
            label={`Delete ${group.name}`}
            title={`Delete the group ${group.name}?`}
            confirm="Delete"
            onConfirm={async () =>
              orThrow("Not deleted", await changed(commands.grantr.deleteGroup(tenant, group.name)))
            }
          >
            <p>
              Every role granted to {group.name} goes with it. Its members keep the roles granted to
              them.
            </p>
          </ConfirmDialog>
        )}
        empty="No groups yet."
      />
      {allowed.has("grantr:add_member") ? (
        <Define tenant={tenant} changed={changed} />
      ) : (
        <p className="text-muted text-sm">
          Choosing a group's members needs reading the tenant's members, which you may not.
        </p>
      )}
    </div>
  );
}

/** A group created, or its members replaced: grantr's one change to a group. */
function Define({
  tenant,
  changed,
}: {
  tenant: string;
  changed: <A>(answer: Promise<A>) => Promise<A>;
}) {
  const { queries, commands } = Route.useRouteContext();
  const { data: members } = useSuspenseQuery(queries.grantr.members(tenant));
  const [defined, define, defining] = useActionState(
    async (_last: { said: string; refused: boolean } | null, form: FormData) => {
      const group = String(form.get("group"));
      const chosen = form.getAll("member").map(String);
      const answer = await changed(
        commands.grantr.defineGroup(
          tenant,
          group,
          members.filter((member) => chosen.includes(named(member))),
        ),
      );
      return answer.outcome === "done"
        ? { said: `${group} has ${chosen.length} members.`, refused: false }
        : { said: refusal("Not saved", answer), refused: true };
    },
    null,
  );
  return (
    <Card render={<section aria-labelledby="define" />} className="flex flex-col gap-3">
      <SectionTitle id="define">Create a group, or replace its members</SectionTitle>
      <form className="flex flex-col gap-3" action={define}>
        <TextField label="Group" name="group" autoComplete="off" required />
        <fieldset className="flex flex-col gap-1">
          <legend className="mb-1 font-semibold text-sm">Members</legend>
          {members.map((member) => (
            <label key={named(member)} className="flex items-center gap-2 text-sm">
              <input type="checkbox" name="member" value={named(member)} />
              {member.id}
            </label>
          ))}
        </fieldset>
        {defined && <p role={defined.refused ? "alert" : "status"}>{defined.said}</p>}
        <Button type="submit" disabled={defining} className="self-start">
          Save the group
        </Button>
      </form>
    </Card>
  );
}
