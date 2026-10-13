import { orThrow } from "@portalr/client";
import { Button, ConfirmDialog, ItemTable } from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { opening, useAccess } from "../../../../../access";
import { type Changing, counted, DefineSet, refused } from "../../../../../define-set";

/**
 * A tenant's roles, for whoever may define them: the built-in ones from grantr's catalog, each
 * with where it may be granted, and the tenant's custom ones, each with its actions. A custom role
 * is created under a name neither built in nor taken, from the actions the catalog says one may
 * hold; an existing one's actions are changed from its row, starting from a fresh read, and a
 * change that takes any out is confirmed, naming them. A custom role is deleted, with its grants,
 * once confirmed. grantr replaces a role's actions whole: the last to save wins (ADR-0025).
 */
export const Route = createFileRoute("/_signed/t/$tenant/access/roles")({
  head: ({ params }) => ({ meta: [{ title: `Roles · ${params.tenant} · portalr admin` }] }),
  beforeLoad: ({ context, params }) => opening(context, params.tenant, "grantr:define_role"),
  loader: ({ context, params }) => {
    const { queries, queryClient } = context;
    return Promise.all([
      queryClient.ensureQueryData(queries.grantr.catalog()),
      queryClient.ensureQueryData(queries.grantr.roles(params.tenant)),
    ]);
  },
  component: Roles,
});

function Roles() {
  const { tenant } = Route.useParams();
  const { queries, commands, queryClient } = Route.useRouteContext();
  const { changed } = useAccess(tenant);
  const { data: catalog } = useSuspenseQuery(queries.grantr.catalog());
  const { data: roles } = useSuspenseQuery(queries.grantr.roles(tenant));
  const [changing, setChanging] = useState<Changing | null>(null);
  const [said, setSaid] = useState<{ said: string; refused: boolean } | null>(null);
  const custom = [...roles].sort((a, b) => a.name.localeCompare(b.name));

  /** Grantr's custom roles now, rather than as last read: a change starts from them. */
  const fresh = () => queryClient.fetchQuery({ ...queries.grantr.roles(tenant), staleTime: 0 });

  async function change(name: string) {
    const current = (await fresh()).find((role) => role.name === name);
    setSaid(current ? null : { said: `${name} is no longer a role.`, refused: true });
    setChanging(current ? { name, chosen: [...current.actions].sort() } : null);
  }

  return (
    <div className="flex flex-col gap-6">
      <ItemTable
        caption="Built-in roles"
        columns={[
          { key: "role", label: "Role", cell: (role) => role.name },
          { key: "kinds", label: "Granted on", cell: (role) => role.kinds.join(", ") },
        ]}
        items={catalog.roles}
        keyOf={(role) => role.name}
        empty={{ title: "No built-in roles", body: "The deployment grants none in a tenant." }}
      />
      <ItemTable
        caption="Custom roles"
        columns={[
          { key: "role", label: "Role", cell: (role) => role.name },
          { key: "actions", label: "Actions", cell: (role) => [...role.actions].sort().join(", ") },
        ]}
        items={custom}
        keyOf={(role) => role.name}
        actions={(role) => (
          <>
            <Button variant="secondary" onClick={() => void change(role.name)}>
              Change actions
            </Button>
            <ConfirmDialog
              label={`Delete ${role.name}`}
              title={`Delete the role ${role.name}?`}
              confirm="Delete"
              onConfirm={async () =>
                orThrow("Not deleted", await changed(commands.grantr.deleteRole(tenant, role.name)))
              }
            >
              <p>Every grant of {role.name} goes with it.</p>
            </ConfirmDialog>
          </>
        )}
        empty={{
          title: "No custom roles yet",
          body: `A custom role holds some of a workspace admin's actions, granted on ${catalog.custom_kinds.join(", ")}.`,
        }}
      />
      {said && <p role={said.refused ? "alert" : "status"}>{said.said}</p>}
      <DefineSet
        key={changing?.name ?? "new"}
        noun="role"
        of="actions"
        changing={changing}
        choices={catalog.custom_actions.map((action) => ({ value: action, label: action }))}
        taken={async (name) => {
          if (catalog.roles.some((role) => role.name === name)) {
            return `${name} is a built-in role. Choose another name.`;
          }
          return (await fresh()).some((role) => role.name === name)
            ? `${name} is a role already. Change its actions from its row.`
            : null;
        }}
        save={async (name, actions) => {
          if (actions.length === 0) {
            return refused("Choose at least one action.");
          }
          const answer = await changed(commands.grantr.defineRole(tenant, name, actions));
          return answer.outcome === "done"
            ? { outcome: "done", result: `${name} holds ${counted(actions.length, "action")}.` }
            : answer;
        }}
        losing={(removed, name) => ({
          title: `Take ${removed.length === 1 ? "this action" : "these actions"} from ${name}?`,
          body: `Whoever holds ${name} loses ${removed.join(", ")}, wherever it is granted.`,
        })}
        onSaved={(message) => {
          setChanging(null);
          setSaid({ said: message, refused: false });
        }}
        onCancel={() => setChanging(null)}
      />
    </div>
  );
}
