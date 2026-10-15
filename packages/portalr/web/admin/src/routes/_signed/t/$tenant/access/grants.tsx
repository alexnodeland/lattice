import { type Answer, type GrantrApi, orThrow, refusal } from "@portalr/client";
import {
  Button,
  Card,
  type Column,
  ConfirmDialog,
  EmptyState,
  ItemTable,
  SectionTitle,
  SelectField,
  TextField,
} from "@portalr/ui";
import { queryOptions, useQuery, useSuspenseQueries } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { type FormEvent, useId, useState } from "react";
import {
  allowedNow,
  byKind,
  fromKey,
  keyOf,
  opening,
  refused,
  type Said,
  useAccess,
  where,
  whom,
  whomIn,
} from "../../../../../access";

type Grant = GrantrApi.components["schemas"]["Grant"];
type AuditEntry = GrantrApi.components["schemas"]["AuditEntry"];
type Resource = GrantrApi.components["schemas"]["Resource"];
type ResourceKind = GrantrApi.components["schemas"]["ResourceKind"];

/** The kinds a grant's form grants to: members and groups. A rule's role isn't offered here. */
const GRANTEE_KINDS = ["user", "service_principal", "group"] as const;

/** The roles that run the tenant: granting one on it is confirmed first. */
const RUNS_THE_TENANT = new Set(["owner", "admin"]);

/** The kinds of resource in a workspace, and those that are an item in one. */
const IN_A_WORKSPACE = new Set<ResourceKind>(["workspace", "thread", "artifact", "rule"]);
const AN_ITEM = new Set<ResourceKind>(["thread", "artifact", "rule"]);

/** A grant as people read it, for its row's name and key: whom, as what, and where. */
const said = (grant: Grant) => `${whom(grant.to)} as ${grant.role} on ${where(grant.on)}`;

/** A member or group from a list, as people read it. */
const whomOf = (grantee: { readonly kind: string; readonly id: string }) => {
  const known = fromKey(keyOf(grantee), GRANTEE_KINDS);
  return known ? whom(known) : keyOf(grantee);
};

/** No read: where grantr doesn't allow a list, the form goes without it. */
const none = queryOptions({
  queryKey: ["grantr", "~none"] as const,
  queryFn: () => null,
  staleTime: Number.POSITIVE_INFINITY,
});

/**
 * Every grant in a tenant, on it and on everything in it, for whoever may grant there, but
 * membership, which is Members': the tenant's grants, then each workspace's, each with whom, its
 * role and where, and revoked, once confirmed, where grantr allows. A role is granted to a member
 * or a group, from the built-in roles grantr's catalog lists, each on the kinds it may be granted
 * on, and the tenant's custom roles, where they may be read. Granting a role that runs the tenant
 * is confirmed. Owner is offered, and its grants revoked, only to those who hold all it holds,
 * as grantr refuses anyone else (ADR-0025).
 */
export const Route = createFileRoute("/_signed/t/$tenant/access/grants")({
  head: ({ params }) => ({ meta: [{ title: `Grants · ${params.tenant} · portalr admin` }] }),
  beforeLoad: ({ context, params }) => opening(context, params.tenant, "grantr:grant"),
  loader: async ({ context, params }) => {
    const { queries, queryClient } = context;
    const allowed = await allowedNow(context, params.tenant);
    await Promise.all([
      queryClient.ensureQueryData(queries.grantr.grants(params.tenant)),
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
  const { queries } = Route.useRouteContext();
  const { allowed } = useAccess(tenant);
  const [
    { data: grants },
    { data: catalog },
    { data: custom },
    { data: members },
    { data: groups },
  ] = useSuspenseQueries({
    queries: [
      queries.grantr.grants(tenant),
      queries.grantr.catalog(),
      allowed.has("grantr:define_role") ? queries.grantr.roles(tenant) : none,
      allowed.has("grantr:add_member") ? queries.grantr.members(tenant) : none,
      allowed.has("grantr:manage_groups") ? queries.grantr.groups(tenant) : none,
    ],
  });
  // Membership is Members' to show and take: grantr gives `member` by adding one.
  const granted = grants.filter((grant) => grant.role !== "member");
  const places = [...new Set(granted.map((grant) => grant.on.workspace ?? null))].sort((a, b) =>
    a === null ? -1 : b === null ? 1 : a.localeCompare(b),
  );
  // Owner holds every action, deleting the tenant among them: only one who may gives or takes it.
  const owns = allowed.has("grantr:delete_tenant");
  // grantr refuses taking the tenant's last owner: so does the page.
  const owners = granted.filter((grant) => grant.role === "owner" && grant.on.kind === "tenant");
  const revocable = (grant: Grant) =>
    (grant.role !== "owner" || owns) && !(owners.length === 1 && owners[0] === grant);
  const roles = [
    ...catalog.roles.filter((role) => owns || role.name !== "owner"),
    ...(custom ?? []).map((role) => ({ name: role.name, kinds: catalog.custom_kinds })),
  ];
  const listed = [
    ...[...(members ?? [])].sort(byKind),
    ...Object.keys(groups ?? {})
      .sort()
      .map((id) => ({ kind: "group", id })),
  ];
  return (
    <div className="flex flex-col gap-6">
      {places.length === 0 && (
        <EmptyState title="No grants yet">Grant a role to a member or a group below.</EmptyState>
      )}
      {places.map((place) => (
        <Granted
          key={place ?? "~tenant"}
          tenant={tenant}
          heading={place === null ? "The tenant" : `Workspace ${place}`}
          grants={granted.filter((grant) => (grant.on.workspace ?? null) === place)}
          revocable={allowed.has("grantr:revoke") ? revocable : null}
        />
      ))}
      <Granting
        tenant={tenant}
        roles={roles}
        listed={listed}
        // Both lists read: choose from them. Either not: type, with what was read suggested.
        typed={members === null || groups === null}
      />
    </div>
  );
}

/** One place's grants, the workspace's before its items', each revoked once confirmed. */
function Granted({
  tenant,
  heading,
  grants,
  revocable,
}: {
  tenant: string;
  /** The place, as its heading names it, and the table under it: "The tenant", "Workspace notes". */
  heading: string;
  grants: readonly Grant[];
  /** Whether grantr would let a grant be revoked; null where revoking isn't allowed at all. */
  revocable: ((grant: Grant) => boolean) | null;
}) {
  const { commands } = Route.useRouteContext();
  const { changed } = useAccess(tenant);
  const sorted = [...grants].sort(
    (a, b) =>
      Number(AN_ITEM.has(a.on.kind)) - Number(AN_ITEM.has(b.on.kind)) ||
      where(a.on).localeCompare(where(b.on)) ||
      whom(a.to).localeCompare(whom(b.to)) ||
      a.role.localeCompare(b.role),
  );
  const headingId = useId();
  // The place is the heading's: an item in it is named, and the place itself isn't again.
  const items = grants.some((grant) => AN_ITEM.has(grant.on.kind));
  const columns: [Column<Grant>, ...Column<Grant>[]] = [
    { key: "to", label: "To", cell: (grant) => whom(grant.to), width: "40%" },
    { key: "role", label: "Role", cell: (grant) => grant.role, width: "20%" },
    ...(items
      ? [
          {
            key: "on",
            label: "On",
            cell: (grant: Grant) =>
              AN_ITEM.has(grant.on.kind) ? `${grant.on.kind} ${grant.on.id}` : "the workspace",
            width: "25%",
          },
        ]
      : []),
  ];
  return (
    <div className="flex flex-col gap-2">
      <SectionTitle id={headingId}>{heading}</SectionTitle>
      <ItemTable
        labelledBy={headingId}
        columns={columns}
        items={sorted}
        keyOf={said}
        named={said}
        actions={
          revocable
            ? (grant) =>
                !revocable(grant) ? null : (
                  <ConfirmDialog
                    label="Revoke"
                    name={`Revoke ${said(grant)}`}
                    title={`Revoke ${grant.role} from ${whomIn(grant.to)}?`}
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
                      They lose what {grant.role} holds on {where(grant.on)}, unless it's granted
                      them another way.
                    </p>
                  </ConfirmDialog>
                )
            : undefined
        }
        empty={{ title: "No grants here", body: "Grant a role below." }}
      />
    </div>
  );
}

/** What the grant form holds: each field, as chosen or typed. */
interface Fields {
  readonly role: string;
  readonly kind: string;
  readonly workspace: string;
  readonly id: string;
  readonly to: string;
}

const EMPTY: Fields = { role: "", kind: "", workspace: "", id: "", to: "" };

/**
 * A role granted on a resource to a member or a group, chosen from `listed`, or typed as
 * `kind:id` with `listed` suggested. Workspaces are suggested from artifactr's. What was entered
 * stays after a refusal; choosing another role chooses where again.
 */
function Granting({
  tenant,
  roles,
  listed,
  typed,
}: {
  tenant: string;
  roles: readonly { readonly name: string; readonly kinds: readonly ResourceKind[] }[];
  listed: readonly { readonly kind: string; readonly id: string }[];
  typed: boolean;
}) {
  const { queries, commands } = Route.useRouteContext();
  const { changed } = useAccess(tenant);
  const heading = useId();
  const suggestedWorkspaces = useId();
  const suggestedGrantees = useId();
  // Suggestions alone, so the form works without them.
  const { data: workspaces } = useQuery(queries.artifactr.workspaces(tenant));
  const [fields, setFields] = useState<Fields>(EMPTY);
  const [answered, setAnswered] = useState<Said>(null);
  const [pending, setPending] = useState(false);
  const set = (field: keyof Fields) => (value: string) =>
    setFields((now) =>
      field === "role" ? { ...now, role: value, kind: "" } : { ...now, [field]: value },
    );
  const kinds = roles.find((role) => role.name === fields.role)?.kinds ?? [];
  const kind = kinds.find((one) => one === fields.kind);
  // Whom the fields name, read once: the grant, its question and what it says done all use it.
  const to = fromKey(fields.to.trim(), GRANTEE_KINDS);
  const confirmed = kind === "tenant" && RUNS_THE_TENANT.has(fields.role) && to !== null;

  /** Where the fields say, once they name a kind of resource. */
  const on = (from: ResourceKind): Resource => {
    const workspace = fields.workspace.trim();
    if (!IN_A_WORKSPACE.has(from)) {
      return { kind: from };
    }
    return AN_ITEM.has(from)
      ? { kind: from, workspace, id: fields.id.trim() }
      : { kind: from, workspace };
  };

  /** The grant the fields name, sent; or why it can't be. */
  async function grant(): Promise<Answer<AuditEntry>> {
    if (kind === undefined || to === null) {
      return refused(
        "name the role, where, and whom, as user:id, service_principal:id or group:id",
      );
    }
    return changed(commands.grantr.grant(tenant, { role: fields.role, on: on(kind), to }));
  }

  /** What a grant done says; the form starts again. */
  function done(): Said {
    const place = kind ? ` on ${where(on(kind))}` : "";
    setFields(EMPTY);
    return { said: `${to ? whom(to) : fields.to} holds ${fields.role}${place}.`, refused: false };
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (confirmed) {
      return;
    }
    setPending(true);
    const answer = await grant();
    setAnswered(
      answer.outcome === "done" ? done() : { said: refusal("Not granted", answer), refused: true },
    );
    setPending(false);
  }

  return (
    <Card render={<section aria-labelledby={heading} />} className="flex flex-col gap-3">
      <SectionTitle id={heading}>Grant a role</SectionTitle>
      <form className="flex flex-col gap-3" onSubmit={(event) => void submit(event)}>
        <SelectField
          label="Role"
          name="role"
          required
          value={fields.role}
          onChange={(event) => set("role")(event.target.value)}
          options={[
            { value: "", label: "Choose a role…" },
            ...roles.map((role) => ({ value: role.name, label: role.name })),
          ]}
        />
        {fields.role !== "" && (
          <SelectField
            label="On"
            name="kind"
            required
            value={kind ?? ""}
            onChange={(event) => set("kind")(event.target.value)}
            options={[
              { value: "", label: "Choose where…" },
              ...kinds.map((one) => ({ value: one, label: one })),
            ]}
          />
        )}
        {kind !== undefined && IN_A_WORKSPACE.has(kind) && (
          <>
            <TextField
              label="Workspace"
              name="workspace"
              autoComplete="off"
              required
              list={suggestedWorkspaces}
              value={fields.workspace}
              onValueChange={(value) => set("workspace")(String(value))}
            />
            <datalist id={suggestedWorkspaces}>
              {(workspaces ?? []).map((workspace) => (
                <option key={workspace} value={workspace} />
              ))}
            </datalist>
          </>
        )}
        {kind !== undefined && AN_ITEM.has(kind) && (
          <TextField
            label={`The ${kind}'s id`}
            name="id"
            autoComplete="off"
            required
            value={fields.id}
            onValueChange={(value) => set("id")(String(value))}
          />
        )}
        {typed ? (
          <>
            <TextField
              label="To, as user:id, service_principal:id or group:id"
              name="to"
              autoComplete="off"
              spellCheck={false}
              required
              list={suggestedGrantees}
              value={fields.to}
              onValueChange={(value) => set("to")(String(value))}
            />
            <datalist id={suggestedGrantees}>
              {listed.map((grantee) => (
                <option key={keyOf(grantee)} value={keyOf(grantee)} label={whomOf(grantee)} />
              ))}
            </datalist>
          </>
        ) : (
          <SelectField
            label="To"
            name="to"
            required
            value={fields.to}
            onChange={(event) => set("to")(event.target.value)}
            options={[
              { value: "", label: "Choose whom…" },
              ...listed.map((grantee) => ({ value: keyOf(grantee), label: whomOf(grantee) })),
            ]}
          />
        )}
        {answered && <p role={answered.refused ? "alert" : "status"}>{answered.said}</p>}
        {confirmed ? (
          <ConfirmDialog
            label="Grant"
            className="self-start"
            title={`Make ${whomIn(to)} ${fields.role} of ${tenant}?`}
            confirm={`Grant ${fields.role}`}
            onConfirm={async () => {
              orThrow("Not granted", await grant());
              setAnswered(done());
            }}
          >
            <p>
              {fields.role === "owner"
                ? `An owner may do anything in ${tenant}, deleting it included.`
                : `An admin may change who may see and do what in ${tenant}, and run every workspace in it.`}
            </p>
          </ConfirmDialog>
        ) : (
          <Button type="submit" disabled={pending} className="self-start">
            Grant
          </Button>
        )}
      </form>
    </Card>
  );
}
