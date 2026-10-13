import { changedAccess, orThrow, refusal } from "@portalr/client";
import {
  Button,
  Card,
  ConfirmDialog,
  ItemTable,
  SectionTitle,
  SelectField,
  TextField,
} from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute, notFound } from "@tanstack/react-router";
import { useActionState, useMemo, useState } from "react";
import { accessIn } from "../../../../../access";

/**
 * A tenant's keys, by public id and principal, for whoever may issue them: a key issued to a
 * service principal, whose secret is shown once, here, and kept nowhere, and a key revoked, once
 * confirmed, where grantr allows.
 */
export const Route = createFileRoute("/_signed/t/$tenant/access/keys")({
  loader: async ({ context, params }) => {
    const { queries, queryClient } = context;
    const checks = accessIn(queries, params.tenant);
    const allowed = checks.select(await queryClient.ensureQueryData(checks));
    if (!allowed.has("grantr:issue_key")) {
      throw notFound();
    }
    await Promise.all([
      queryClient.ensureQueryData(queries.grantr.keyring(params.tenant)),
      allowed.has("grantr:add_member") &&
        queryClient.ensureQueryData(queries.grantr.members(params.tenant)),
    ]);
  },
  component: Keys,
});

function Keys() {
  const { tenant } = Route.useParams();
  const { queries, commands, queryClient } = Route.useRouteContext();
  const checks = useMemo(() => accessIn(queries, tenant), [queries, tenant]);
  const { data: allowed } = useSuspenseQuery(checks);
  const { data: keys } = useSuspenseQuery(queries.grantr.keyring(tenant));
  const changed = <A,>(answer: Promise<A>) => changedAccess(queryClient, tenant, answer);
  return (
    <div className="flex flex-col gap-6">
      <ItemTable
        caption="Keys"
        columns={[
          { label: "Key", cell: (key) => <code className="font-mono">{key.id}</code> },
          { label: "Service principal", cell: (key) => key.principal.id },
        ]}
        items={[...keys].sort((a, b) => a.id.localeCompare(b.id))}
        keyOf={(key) => key.id}
        {...(allowed.has("grantr:revoke_key") && {
          actions: (key: (typeof keys)[number]) => (
            <ConfirmDialog
              label={`Revoke ${key.id}`}
              title={`Revoke the key ${key.id}?`}
              confirm="Revoke"
              onConfirm={async () =>
                orThrow("Not revoked", await changed(commands.grantr.revokeKey(tenant, key.id)))
              }
            >
              <p>{key.principal.id} can't use it again. Its other keys, and its roles, stay.</p>
            </ConfirmDialog>
          ),
        })}
        empty="No keys yet."
      />
      <Issue tenant={tenant} listsMembers={allowed.has("grantr:add_member")} changed={changed} />
    </div>
  );
}

/**
 * A key issued to a service principal, chosen from the tenant's where they may be read, or named
 * otherwise. Its secret is shown once, from this form's state alone: no read or link holds it.
 */
function Issue({
  tenant,
  listsMembers,
  changed,
}: {
  tenant: string;
  listsMembers: boolean;
  changed: <A>(answer: Promise<A>) => Promise<A>;
}) {
  const { commands } = Route.useRouteContext();
  const [copied, setCopied] = useState(false);
  const [issued, issue, issuing] = useActionState(
    async (_last: { secret: string | null; said: string } | null, form: FormData) => {
      setCopied(false);
      const principal = String(form.get("principal"));
      const answer = await changed(commands.grantr.issueKey(tenant, principal));
      return answer.outcome === "done"
        ? { secret: answer.result.key, said: `A key for ${principal}.` }
        : { secret: null, said: refusal("Not issued", answer) };
    },
    null,
  );
  return (
    <Card render={<section aria-labelledby="issue" />} className="flex flex-col gap-3">
      <SectionTitle id="issue">Issue a key</SectionTitle>
      <form className="flex flex-col gap-3" action={issue}>
        {listsMembers ? (
          <Principals tenant={tenant} />
        ) : (
          <TextField label="Service principal" name="principal" autoComplete="off" required />
        )}
        <Button type="submit" disabled={issuing} className="self-start">
          Issue
        </Button>
      </form>
      {issued?.secret === null && <p role="alert">{issued.said}</p>}
      {issued?.secret && (
        <div role="status" className="flex flex-col gap-2">
          <p>{issued.said} Copy it now: it isn't shown again, and grantr keeps only its digest.</p>
          <TextField label="The key" value={issued.secret} readOnly className="font-mono" />
          <Button
            variant="secondary"
            className="self-start"
            onClick={() => {
              void navigator.clipboard
                ?.writeText(issued.secret ?? "")
                .then(() => setCopied(true))
                .catch(() => setCopied(false));
            }}
          >
            {copied ? "Copied" : "Copy the key"}
          </Button>
        </div>
      )}
    </Card>
  );
}

/** The tenant's service principals, to issue a key to one. */
function Principals({ tenant }: { tenant: string }) {
  const { queries } = Route.useRouteContext();
  const { data: members } = useSuspenseQuery(queries.grantr.members(tenant));
  const principals = members.filter((member) => member.kind === "service_principal");
  if (principals.length === 0) {
    return <p className="text-muted text-sm">Add a service principal under Members first.</p>;
  }
  return (
    <SelectField
      label="Service principal"
      name="principal"
      options={principals.map((principal) => ({ value: principal.id, label: principal.id }))}
    />
  );
}
