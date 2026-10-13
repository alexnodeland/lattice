import { orThrow } from "@portalr/client";
import { Button, ConfirmDialog, ItemTable } from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { type ComponentProps, useState } from "react";
import { allowedNow, byKind, fromKey, keyOf, opening, useAccess, who } from "../../../../../access";
import { type Changing, counted, DefineSet, refused } from "../../../../../define-set";

/** The kinds of member a group's form takes. */
const MEMBER_KINDS = ["user", "service_principal"] as const;

/** A member's `kind:id` as people read it, or the key itself where it names none. */
const named = (key: string) => {
  const member = fromKey(key, MEMBER_KINDS);
  return member ? who(member) : key;
};

/**
 * A tenant's groups, each with its members, for whoever may manage them. A group is created under
 * a name not yet taken; an existing one's members are changed from its row, starting from a fresh
 * read, and a change that drops anyone is confirmed, naming them. A group is deleted, with its
 * grants, once confirmed. Members are chosen from the tenant's where they may be read, which
 * adding one allows, and typed as `kind:id` otherwise. grantr replaces a group's members whole:
 * the last to save wins (portalr ADR-0024).
 */
export const Route = createFileRoute("/_signed/t/$tenant/access/groups")({
  head: ({ params }) => ({ meta: [{ title: `Groups · ${params.tenant} · portalr admin` }] }),
  beforeLoad: ({ context, params }) => opening(context, params.tenant, "grantr:manage_groups"),
  loader: async ({ context, params }) => {
    const { queries, queryClient } = context;
    const allowed = await allowedNow(context, params.tenant);
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
  const { allowed, changed } = useAccess(tenant);
  const { data: groups } = useSuspenseQuery(queries.grantr.groups(tenant));
  const [changing, setChanging] = useState<Changing | null>(null);
  const [said, setSaid] = useState<{ said: string; refused: boolean } | null>(null);
  const listed = Object.entries(groups)
    .map(([name, members]) => ({ name, members: [...members].sort(byKind) }))
    .sort((a, b) => a.name.localeCompare(b.name));

  /** Grantr's groups now, rather than as last read: a change starts from them. */
  const fresh = () => queryClient.fetchQuery({ ...queries.grantr.groups(tenant), staleTime: 0 });

  async function change(name: string) {
    const current = (await fresh())[name];
    setSaid(current ? null : { said: `${name} is no longer a group.`, refused: true });
    setChanging(current ? { name, chosen: current.map(keyOf) } : null);
  }

  const define: Omit<ComponentProps<typeof DefineSet>, "choices"> = {
    noun: "group",
    of: "members",
    changing,
    typed: "Members, as user:id or service_principal:id, separated by commas",
    taken: async (name) =>
      name in (await fresh())
        ? `${name} is a group already. Change its members from its row.`
        : null,
    save: async (name, chosen) => {
      const parsed = chosen.map((key) => fromKey(key, MEMBER_KINDS));
      const bad = chosen.filter((_, index) => parsed[index] === null);
      if (bad.length > 0) {
        return refused(
          `Write each member as user:id or service_principal:id, not ${bad.join(", ")}.`,
        );
      }
      const members = parsed.filter((member) => member !== null);
      const answer = await changed(commands.grantr.defineGroup(tenant, name, members));
      return answer.outcome === "done"
        ? { outcome: "done", result: `${name} has ${counted(members.length, "member")}.` }
        : answer;
    },
    losing: (removed, name) => {
      const one = removed.length === 1;
      return {
        title: `Take ${one ? "this member" : "these members"} out of ${name}?`,
        body: `${removed.map(named).join(", ")} ${one ? "loses" : "lose"} every role granted to ${name}, and ${one ? "keeps" : "keep"} those granted to them.`,
      };
    },
    onSaved: (message) => {
      setChanging(null);
      setSaid({ said: message, refused: false });
    },
    onCancel: () => setChanging(null),
  };

  return (
    <div className="flex flex-col gap-6">
      <ItemTable
        caption="Groups"
        columns={[
          { key: "group", label: "Group", cell: (group) => group.name },
          {
            key: "members",
            label: "Members",
            cell: (group) => group.members.map(who).join(", ") || "None",
          },
        ]}
        items={listed}
        keyOf={(group) => group.name}
        actions={(group) => (
          <>
            <Button variant="secondary" onClick={() => void change(group.name)}>
              Change members
            </Button>
            <ConfirmDialog
              label={`Delete ${group.name}`}
              title={`Delete the group ${group.name}?`}
              confirm="Delete"
              onConfirm={async () =>
                orThrow(
                  "Not deleted",
                  await changed(commands.grantr.deleteGroup(tenant, group.name)),
                )
              }
            >
              <p>
                Every role granted to {group.name} goes with it. Its members keep the roles granted
                to them.
              </p>
            </ConfirmDialog>
          </>
        )}
        empty={{ title: "No groups yet", body: "A group's grants reach each of its members." }}
      />
      {said && <p role={said.refused ? "alert" : "status"}>{said.said}</p>}
      {allowed.has("grantr:add_member") ? (
        <FromMembers key={changing?.name ?? "new"} tenant={tenant} define={define} />
      ) : (
        <DefineSet key={changing?.name ?? "new"} {...define} choices={null} />
      )}
    </div>
  );
}

/** The form, choosing from the tenant's members, people first. */
function FromMembers({
  tenant,
  define,
}: {
  tenant: string;
  define: Omit<ComponentProps<typeof DefineSet>, "choices">;
}) {
  const { queries } = Route.useRouteContext();
  const { data: members } = useSuspenseQuery(queries.grantr.members(tenant));
  return (
    <DefineSet
      {...define}
      choices={[...members].sort(byKind).map((member) => ({
        value: keyOf(member),
        label: who(member),
      }))}
    />
  );
}
