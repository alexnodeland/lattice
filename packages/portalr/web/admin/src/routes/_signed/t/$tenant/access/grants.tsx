import { type GrantrApi, orThrow, refusal } from "@portalr/client";
import {
  Button,
  Card,
  ConfirmDialog,
  ItemTable,
  SectionTitle,
  SelectField,
  TextField,
} from "@portalr/ui";
import { useQuery, useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useActionState, useId, useState } from "react";
import {
  allowedNow,
  byKind,
  fromKey,
  keyOf,
  opening,
  useAccess,
  where,
  whom,
} from "../../../../../access";

type Grant = GrantrApi.components["schemas"]["Grant"];
type Resource = GrantrApi.components["schemas"]["Resource"];
type ResourceKind = GrantrApi.components["schemas"]["ResourceKind"];

/** The kinds a grant's form grants to: members and groups. A rule holds its own role, granted apart. */
const GRANTEE_KINDS = ["user", "service_principal", "group"] as const;

/** A grant's identity, for a list's key: its role, where, and to whom. */
const grantKey = (grant: Grant) => `${grant.role}|${where(grant.on)}|${whom(grant.to)}`;

/** The resource a grant is on, from its kind, its workspace and its item. */
function resourceOf(kind: ResourceKind, workspace: string, id: string): Resource {
  if (kind === "tenant" || kind === "deployment") {
    return { kind };
  }
  return kind === "workspace" ? { kind, workspace } : { kind, workspace, id };
}

/** How broad each kind of resource is: the tenant before its workspaces, before their items. */
const BREADTH: Record<ResourceKind, number> = {
  deployment: 0,
  tenant: 1,
  workspace: 2,
  thread: 3,
  artifact: 3,
  rule: 3,
};

/** Resources broadest first, then by workspace, kind and id. */
const broadest = (a: Resource, b: Resource) =>
  BREADTH[a.kind] - BREADTH[b.kind] ||
  (a.workspace ?? "").localeCompare(b.workspace ?? "") ||
  a.kind.localeCompare(b.kind) ||
  (a.id ?? "").localeCompare(b.id ?? "");

/**
 * Every grant in a tenant, on it and on everything in it, for whoever may grant there, but
 * membership, which is Members': each role, where, and to whom, the broadest first, and revoked,
 * once confirmed, where grantr allows. A role is granted to a member or a group, from the
 * built-in roles grantr's catalog lists, each on the kinds it may be granted on, and the tenant's
 * custom roles, where they may be read. grantr checks each grant on its resource; the form shows
 * where the tenant allows granting (ADR-0025).
 */
export const Route = createFileRoute("/_signed/t/$tenant/access/grants")({
  head: ({ params }) => ({ meta: [{ title: `Grants · ${params.tenant} · portalr admin` }] }),
  beforeLoad: ({ context, params }) => opening(context, params.tenant, "grantr:grant"),
  loader: async ({ context, params }) => {
    const { queries, queryClient } = context;
    const allowed = await allowedNow(context, params.tenant);
    await Promise.all([
      queryClient.ensureQueryData(queries.grantr.tenantGrants(params.tenant)),
      queryClient.ensureQueryData(queries.grantr.catalog()),
      allowed.has("grantr:define_role") &&
        queryClient.ensureQueryData(queries.grantr.roles(params.tenant)),
      allowed.has("grantr:add_member") &&
        queryClient.ensureQueryData(queries.grantr.members(params.tenant)),
      allowed.has("grantr:manage_groups") &&
        queryClient.ensureQueryData(queries.grantr.groups(params.tenant)),
    ]);
  },
  component: Grants,
});

function Grants() {
  const { tenant } = Route.useParams();
  const { queries, commands } = Route.useRouteContext();
  const { allowed, changed } = useAccess(tenant);
  const { data: grants } = useSuspenseQuery(queries.grantr.tenantGrants(tenant));
  // Membership is Members' to show and take: grantr gives `member` by adding one.
  const sorted = [...grants.filter((grant) => grant.role !== "member")].sort(
    (a, b) =>
      broadest(a.on, b.on) || a.role.localeCompare(b.role) || whom(a.to).localeCompare(whom(b.to)),
  );
  return (
    <div className="flex flex-col gap-6">
      <ItemTable
        caption="Grants"
        columns={[
          { key: "role", label: "Role", cell: (grant) => grant.role },
          { key: "on", label: "On", cell: (grant) => where(grant.on) },
          { key: "to", label: "To", cell: (grant) => whom(grant.to) },
        ]}
        items={sorted}
        keyOf={grantKey}
        actions={
          allowed.has("grantr:revoke")
            ? (grant) => (
                <ConfirmDialog
                  label={`Revoke ${grant.role} from ${whom(grant.to)} on ${where(grant.on)}`}
                  title={`Revoke ${grant.role} from ${whom(grant.to)}?`}
                  confirm="Revoke"
                  onConfirm={async () =>
                    orThrow(
                      "Not revoked",
                      await changed(
                        commands.grantr.revoke(tenant, {
                          role: grant.role,
                          on: grant.on,
                          to: grant.to,
                        }),
                      ),
                    )
                  }
                >
                  <p>
                    They lose what {grant.role} holds on {where(grant.on)}, unless it's granted them
                    another way.
                  </p>
                </ConfirmDialog>
              )
            : undefined
        }
        empty={{ title: "No grants yet", body: "Grant a role to a member or a group below." }}
      />
      <Granting tenant={tenant} />
    </div>
  );
}

/**
 * A role granted on a resource to a member or a group. Members and groups are chosen from the
 * tenant's where either may be read, and typed as `kind:id` otherwise.
 */
function Granting({ tenant }: { tenant: string }) {
  const { queries, commands } = Route.useRouteContext();
  const { allowed, changed } = useAccess(tenant);
  const heading = useId();
  const { data: catalog } = useSuspenseQuery(queries.grantr.catalog());
  // Each list where grantr allows it, which the loader read: not asked for otherwise.
  const custom = useQuery({
    ...queries.grantr.roles(tenant),
    enabled: allowed.has("grantr:define_role"),
  });
  const members = useQuery({
    ...queries.grantr.members(tenant),
    enabled: allowed.has("grantr:add_member"),
  });
  const groups = useQuery({
    ...queries.grantr.groups(tenant),
    enabled: allowed.has("grantr:manage_groups"),
  });
  const roles = [
    ...catalog.roles,
    ...(custom.data ?? []).map((role) => ({ name: role.name, kinds: catalog.custom_kinds })),
  ];
  const [role, setRole] = useState(roles[0]?.name ?? "");
  const kinds = roles.find((one) => one.name === role)?.kinds ?? [];
  const [chosenKind, setKind] = useState<ResourceKind | "">("");
  const kind = chosenKind !== "" && kinds.includes(chosenKind) ? chosenKind : kinds[0];
  const grantees = [
    ...[...(members.data ?? [])].sort(byKind),
    ...Object.keys(groups.data ?? {})
      .sort()
      .map((id) => ({ kind: "group" as const, id })),
  ];

  const [said, grant, granting] = useActionState(
    async (_last: { said: string; refused: boolean } | null, form: FormData) => {
      const to = fromKey(String(form.get("to") ?? ""), GRANTEE_KINDS);
      if (kind === undefined || to === null) {
        return {
          said: "Not granted: name a role, and whom, as user:id, service_principal:id or group:id.",
          refused: true,
        };
      }
      const on = resourceOf(
        kind,
        String(form.get("workspace") ?? ""),
        String(form.get("id") ?? ""),
      );
      const answer = await changed(commands.grantr.grant(tenant, { role, on, to }));
      return answer.outcome === "done"
        ? { said: `${whom(to)} holds ${role} on ${where(on)}.`, refused: false }
        : { said: refusal("Not granted", answer), refused: true };
    },
    null,
  );

  return (
    <Card render={<section aria-labelledby={heading} />} className="flex flex-col gap-3">
      <SectionTitle id={heading}>Grant a role</SectionTitle>
      <form className="flex flex-col gap-3" action={grant}>
        <SelectField
          label="Role"
          name="role"
          value={role}
          onChange={(event) => setRole(event.target.value)}
          options={roles.map((one) => ({ value: one.name, label: one.name }))}
        />
        <SelectField
          label="On"
          name="kind"
          value={kind ?? ""}
          onChange={(event) => setKind(kinds.find((one) => one === event.target.value) ?? "")}
          options={kinds.map((one) => ({ value: one, label: one }))}
        />
        {kind !== undefined && kind !== "tenant" && kind !== "deployment" && (
          <TextField label="Workspace" name="workspace" autoComplete="off" required />
        )}
        {kind !== undefined && !["tenant", "deployment", "workspace"].includes(kind) && (
          <TextField label={`The ${kind}'s id`} name="id" autoComplete="off" required />
        )}
        {grantees.length > 0 ? (
          <SelectField
            label="To"
            name="to"
            options={grantees.map((grantee) => ({ value: keyOf(grantee), label: whom(grantee) }))}
          />
        ) : (
          <TextField
            label="To, as user:id, service_principal:id or group:id"
            name="to"
            autoComplete="off"
            spellCheck={false}
            required
          />
        )}
        {said && <p role={said.refused ? "alert" : "status"}>{said.said}</p>}
        <Button type="submit" disabled={granting} className="self-start">
          Grant
        </Button>
      </form>
    </Card>
  );
}
