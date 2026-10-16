import { orThrow } from "@portalr/client";
import { Button, ConfirmDialog, ItemTable } from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { counted, opening, possessive, refused, type Said, useAccess } from "../../../../../access";
import { type Changing, DefineSet } from "../../../../../define-set";

/** The role form's words, and its rows' Change, which names the role it changes. */
const WORDS = {
  name: "Role",
  of: "Actions",
  create: "Create a role",
  change: (name: string) => `Change ${possessive(name)} actions`,
  created: "Create the role",
  saved: "Save the role",
};

/**
 * A tenant's roles, for whoever may define them: the built-in ones from grantr's catalog, each
 * with where it may be granted, and the tenant's custom ones, each with its actions. A custom role
 * is created under a name not taken, from the actions the catalog says one may hold, grouped by
 * library; an existing one's actions are changed from its row, starting from a fresh read, and a
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
  const [said, setSaid] = useState<Said>(null);
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
            <Button
              variant="ghost"
              size="sm"
              aria-label={WORDS.change(role.name)}
              onClick={() => void change(role.name)}
            >
              Change actions
            </Button>
            <ConfirmDialog
              label="Delete"
              about={role.name}
              look="danger-soft"
              size="sm"
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
        words={WORDS}
        changing={changing}
        // Each action under its library, such as reflexr's.
        picking={{
          choices: catalog.custom_actions.map((action) => ({
            value: action,
            label: action,
            group: action.slice(0, action.indexOf(":")),
          })),
        }}
        note={
          <p className="text-muted text-sm">
            An action added here is added wherever {changing?.name} is granted.
          </p>
        }
        // grantr refuses a built-in role's name, and says so.
        taken={async (name) =>
          (await fresh()).some((role) => role.name === name)
            ? `${name} is a role already. Change its actions from its row.`
            : null
        }
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
