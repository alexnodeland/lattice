import { orThrow, refusal } from "@portalr/client";
import {
  Alert,
  Button,
  Card,
  ConfirmDialog,
  ItemTable,
  pageTitle,
  SectionTitle,
  SelectField,
  TextField,
} from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useActionState, useId, useState } from "react";
import { allowedNow, opening, useAccess } from "../../../../../access";

/** A key just issued: its public id, its principal, and its secret, held by this screen alone. */
interface Issued {
  readonly id: string | null;
  readonly principal: string;
  readonly secret: string;
}

/**
 * A tenant's keys, by public id and principal, for whoever may issue them: a key issued to a
 * service principal, whose secret is shown once, here, until Done, leaving, or the key's
 * revocation, and kept nowhere, and a key revoked, once confirmed, where grantr allows.
 */
export const Route = createFileRoute("/_signed/t/$tenant/access/keys")({
  head: ({ params, match }) => ({
    meta: [{ title: pageTitle(match.context.config.brand, "admin", `Keys · ${params.tenant}`) }],
  }),
  beforeLoad: ({ context, params }) => opening(context, params.tenant, "grantr:issue_key"),
  loader: async ({ context, params }) => {
    const { queries, queryClient } = context;
    const allowed = await allowedNow(context, params.tenant);
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
  const { queries, commands } = Route.useRouteContext();
  const { allowed, changed } = useAccess(tenant);
  const { data: keys } = useSuspenseQuery(queries.grantr.keyring(tenant));
  const [issued, setIssued] = useState<Issued | null>(null);
  return (
    <div className="flex flex-col gap-6">
      <ItemTable
        caption="Keys"
        columns={[
          { key: "key", label: "Key", cell: (key) => <code className="font-mono">{key.id}</code> },
          { key: "principal", label: "Service principal", cell: (key) => key.principal.id },
        ]}
        items={[...keys].sort((a, b) => a.id.localeCompare(b.id))}
        keyOf={(key) => key.id}
        actions={
          allowed.has("grantr:revoke_key")
            ? (key) => (
                <ConfirmDialog
                  label="Revoke"
                  about={key.id}
                  look="danger-soft"
                  size="sm"
                  title={`Revoke the key ${key.id}?`}
                  confirm="Revoke"
                  onConfirm={async () => {
                    orThrow(
                      "Not revoked",
                      await changed(commands.grantr.revokeKey(tenant, key.id)),
                    );
                    setIssued((shown) => (shown?.id === key.id ? null : shown));
                  }}
                >
                  <p>{key.principal.id} can't use it again. Its other keys, and its roles, stay.</p>
                </ConfirmDialog>
              )
            : undefined
        }
        empty={{ title: "No keys yet", body: "A service principal signs in with a key." }}
      />
      {allowed.has("grantr:add_member") ? (
        <IssueToListed tenant={tenant} issued={issued} onIssued={setIssued} />
      ) : (
        <Issue tenant={tenant} principals={null} issued={issued} onIssued={setIssued} />
      )}
    </div>
  );
}

/** Issue, choosing from the tenant's service principals: with none, there is no one to issue to. */
function IssueToListed(props: { tenant: string; issued: Issued | null; onIssued: Shown }) {
  const { queries } = Route.useRouteContext();
  const { data: members } = useSuspenseQuery(queries.grantr.members(props.tenant));
  const principals = members
    .filter((member) => member.kind === "service_principal")
    .map((member) => member.id)
    .sort();
  if (principals.length === 0) {
    return (
      <p className="text-muted text-sm">
        A key is issued to a service principal. Add one under Members first.
      </p>
    );
  }
  return <Issue {...props} principals={principals} />;
}

type Shown = (issued: Issued | null) => void;

/**
 * A key issued to a service principal, chosen from `principals`, or named where they can't be
 * read. Its secret is shown once, from this screen's state alone: no read or link holds it.
 */
function Issue({
  tenant,
  principals,
  issued,
  onIssued,
}: {
  tenant: string;
  principals: readonly string[] | null;
  issued: Issued | null;
  onIssued: Shown;
}) {
  const { commands } = Route.useRouteContext();
  const { changed } = useAccess(tenant);
  const heading = useId();
  const [copied, setCopied] = useState<boolean | null>(null);
  const [refused, issue, issuing] = useActionState(async (_last: string | null, form: FormData) => {
    setCopied(null);
    onIssued(null);
    const principal = form.get("principal");
    if (typeof principal !== "string" || principal === "") {
      return "Not issued: choose a service principal.";
    }
    const answer = await changed(commands.grantr.issueKey(tenant, principal));
    if (answer.outcome === "refused") {
      return refusal("Not issued", answer);
    }
    const { event } = answer.result.entry;
    onIssued({
      id: event.type === "key_issued" ? event.key : null,
      principal,
      secret: answer.result.key,
    });
    return null;
  }, null);
  return (
    <Card render={<section aria-labelledby={heading} />} className="flex flex-col gap-3">
      <SectionTitle id={heading}>Issue a key</SectionTitle>
      <form className="flex flex-col gap-3" action={issue}>
        {principals === null ? (
          <TextField label="Service principal" name="principal" autoComplete="off" required />
        ) : (
          <SelectField
            label="Service principal"
            name="principal"
            options={principals.map((principal) => ({ value: principal, label: principal }))}
          />
        )}
        <Button type="submit" disabled={issuing} className="self-start">
          Issue
        </Button>
      </form>
      {refused && <Alert tone="error">{refused}</Alert>}
      {issued && (
        <div role="status" className="flex flex-col gap-2">
          <p>
            A key for {issued.principal}. Copy it now: it isn't shown again, and grantr keeps only
            its digest.
          </p>
          <TextField
            label="The key"
            value={issued.secret}
            readOnly
            spellCheck={false}
            className="font-mono"
          />
          {copied === false && (
            <Alert tone="error">It couldn't be copied here: select it, and copy it yourself.</Alert>
          )}
          <div className="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              onClick={() => {
                // Where the page isn't a secure context, there is no clipboard to write to.
                Promise.resolve()
                  .then(() => navigator.clipboard.writeText(issued.secret))
                  .then(() => setCopied(true))
                  .catch(() => setCopied(false));
              }}
            >
              {copied ? "Copied" : "Copy the key"}
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                setCopied(null);
                onIssued(null);
              }}
            >
              Done
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
}
