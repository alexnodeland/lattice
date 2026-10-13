import { type Answer, type GrantrApi, orThrow, type Refusal, refusal } from "@portalr/client";
import {
  Button,
  Card,
  CheckboxGroup,
  ConfirmDialog,
  ItemTable,
  SectionTitle,
  TextField,
} from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useActionState, useId, useState } from "react";
import { allowedNow, byKind, opening, useAccess, who } from "../../../../../access";

type Member = GrantrApi.components["schemas"]["Member"];

/** A member as a group's form names it, `kind:id`, since grantr keeps the kinds apart. */
const keyOf = (member: Member) => `${member.kind}:${member.id}`;

/** A member from its `kind:id`, or null where it names no kind grantr has. */
function fromKey(key: string): Member | null {
  const at = key.indexOf(":");
  const kind = key.slice(0, at);
  const id = key.slice(at + 1);
  if (at < 0 || id === "") {
    return null;
  }
  return kind === "user" || kind === "service_principal" ? { kind, id } : null;
}

/** "1 member", "2 members". */
const members = (count: number) => `${count} ${count === 1 ? "member" : "members"}`;

/** A group being changed: its name, and its members as grantr last said, read afresh. */
interface Changing {
  readonly name: string;
  readonly members: readonly Member[];
}

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
    const now = await fresh();
    const current = now[name];
    setSaid(current ? null : { said: `${name} is no longer a group.`, refused: true });
    setChanging(current ? { name, members: current } : null);
  }

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
      <Define
        key={changing?.name ?? "new"}
        tenant={tenant}
        changing={changing}
        listsMembers={allowed.has("grantr:add_member")}
        taken={async (name) => name in (await fresh())}
        onSaved={(message) => {
          setChanging(null);
          setSaid({ said: message, refused: false });
        }}
        onCancel={() => setChanging(null)}
      />
    </div>
  );
}

/**
 * A group created, or an existing one's members changed: grantr's one change to a group, which
 * replaces its members whole.
 */
function Define({
  tenant,
  changing,
  listsMembers,
  taken,
  onSaved,
  onCancel,
}: {
  tenant: string;
  changing: Changing | null;
  listsMembers: boolean;
  taken: (name: string) => Promise<boolean>;
  onSaved: (said: string) => void;
  onCancel: () => void;
}) {
  const { commands } = Route.useRouteContext();
  const { changed } = useAccess(tenant);
  const heading = useId();
  const [name, setName] = useState("");
  const [chosen, setChosen] = useState<readonly string[]>(changing?.members.map(keyOf) ?? []);
  const [typed, setTyped] = useState(chosen.join(", "));
  const keys = listsMembers ? chosen : typed.split(/[\s,]+/).filter((key) => key !== "");
  const group = changing?.name ?? name.trim();
  const removed = (changing?.members ?? []).filter((member) => !keys.includes(keyOf(member)));
  const one = removed.length === 1;

  /** Saved, or why not: a name taken, a member that isn't one, or grantr's refusal. */
  async function save(): Promise<Answer<string>> {
    const parsed = keys.map(fromKey);
    const bad = keys.filter((_, index) => parsed[index] === null);
    if (bad.length > 0) {
      return refused(
        `Write each member as user:id or service_principal:id, not ${bad.join(", ")}.`,
      );
    }
    if (changing === null && (await taken(group))) {
      return refused(`${group} is a group already. Change its members from its row.`);
    }
    const chosenMembers = parsed.filter((member) => member !== null);
    const answer = await changed(commands.grantr.defineGroup(tenant, group, chosenMembers));
    return answer.outcome === "done"
      ? { outcome: "done", result: `${group} has ${members(chosenMembers.length)}.` }
      : answer;
  }

  const [said, submit, saving] = useActionState(async (_last: string | null) => {
    const saved = await save();
    if (saved.outcome === "refused") {
      return refusal("Not saved", saved);
    }
    onSaved(saved.result);
    return null;
  }, null);

  return (
    <Card render={<section aria-labelledby={heading} />} className="flex flex-col gap-3">
      <SectionTitle id={heading}>
        {changing ? `Change ${changing.name}'s members` : "Create a group"}
      </SectionTitle>
      <form className="flex flex-col gap-3" action={submit}>
        {changing === null && (
          <TextField
            label="Group"
            name="group"
            autoComplete="off"
            required
            value={name}
            onValueChange={(value) => setName(String(value))}
          />
        )}
        {listsMembers ? (
          <Choices tenant={tenant} value={chosen} onValueChange={setChosen} />
        ) : (
          <TextField
            label="Members, as user:id or service_principal:id, separated by commas"
            name="members"
            autoComplete="off"
            spellCheck={false}
            value={typed}
            onValueChange={(value) => setTyped(String(value))}
          />
        )}
        {said && <p role="alert">{said}</p>}
        <div className="flex flex-wrap gap-2">
          {removed.length > 0 ? (
            <ConfirmDialog
              label="Save the group"
              title={`Take ${one ? "this member" : "these members"} out of ${group}?`}
              confirm="Save the group"
              onConfirm={async () => onSaved(orThrow("Not saved", await save()))}
            >
              <p>
                {`${removed.map(who).join(", ")} ${one ? "loses" : "lose"} every role granted to ${group}, and ${one ? "keeps" : "keep"} those granted to them.`}
              </p>
            </ConfirmDialog>
          ) : (
            <Button type="submit" disabled={saving}>
              {changing ? "Save the group" : "Create the group"}
            </Button>
          )}
          {changing && (
            <Button variant="secondary" onClick={onCancel}>
              Cancel
            </Button>
          )}
        </div>
      </form>
    </Card>
  );
}

/** A refusal of the form's own, before grantr is asked: no status, and why. */
const refused = (reason: string): Refusal => ({ outcome: "refused", status: 0, reasons: [reason] });

/** The tenant's members, people first, to check those in the group. */
function Choices({
  tenant,
  value,
  onValueChange,
}: {
  tenant: string;
  value: readonly string[];
  onValueChange: (value: readonly string[]) => void;
}) {
  const { queries } = Route.useRouteContext();
  const { data: tenantMembers } = useSuspenseQuery(queries.grantr.members(tenant));
  return (
    <CheckboxGroup
      legend="Members"
      choices={[...tenantMembers].sort(byKind).map((member) => ({
        value: keyOf(member),
        label: who(member),
      }))}
      value={value}
      onValueChange={onValueChange}
    />
  );
}
