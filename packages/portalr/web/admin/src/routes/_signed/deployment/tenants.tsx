import { keys, orThrow } from "@portalr/client";
import {
  Alert,
  Button,
  Card,
  ConfirmDialog,
  ItemTable,
  PageHeader,
  SectionTitle,
  TextField,
} from "@portalr/ui";
import { useQueryClient, useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute, type ErrorComponentProps } from "@tanstack/react-router";
import { useId, useMemo, useRef, useState } from "react";
import { unread } from "../../../home";
import { ReadFailed } from "../../../read-failed";
import { budgetSaid, isEmail, isTenantId, PAGE, rowsFor, spendSaid } from "../../../tenants";

const HEADER = <PageHeader title="Tenants" meta="Every tenant in grantr, and what it spends" />;

/**
 * Every tenant, for the deployment's operators: each with its LiteLLM team's spend and budget, a
 * page at a time, and a tenant created with its first owner, by email, once confirmed (portalr
 * ADR-0034). Tenants are not entered from here: admin opens a tenant to its own owners and admins.
 */
export const Route = createFileRoute("/_signed/deployment/tenants")({
  head: ({ match }) => ({
    meta: [{ title: match.context.title("Tenants") }],
  }),
  // The deployment's layout read it before letting an operator in.
  loader: ({ context }) =>
    context.queryClient.ensureQueryData(context.queries.portalr.tenants(context.user)),
  component: Tenants,
  errorComponent: ({ error, reset }: ErrorComponentProps) => (
    <ReadFailed title="Tenants couldn't be read" header={HEADER} error={error} reset={reset} />
  ),
});

function Tenants() {
  const { queries, user } = Route.useRouteContext();
  const { data: every } = useSuspenseQuery(queries.portalr.tenants(user));
  const [shown, setShown] = useState(PAGE);
  // The layout let only an operator in, so there is a read; sorted when it changes, not on each render.
  const rows = useMemo(() => rowsFor(every), [every]);
  const answered = every?.spend.status === "ok";
  return (
    <div className="flex flex-col gap-8">
      {HEADER}
      {every && every.spend.status !== "ok" && (
        <Alert tone="warn">
          {unread("LiteLLM", every.spend).line} Spend and budgets are not shown.
        </Alert>
      )}
      <ItemTable
        caption="Tenants"
        columns={[
          { key: "tenant", label: "Tenant", cell: (row) => row.tenant },
          { key: "spend", label: "Spend", numeric: true, cell: (row) => spendSaid(row) },
          { key: "budget", label: "Budget", cell: (row) => budgetSaid(row, answered) },
        ]}
        items={rows.slice(0, shown)}
        keyOf={(row) => row.tenant}
        empty={{ title: "No tenants yet", body: "Create the first one below." }}
      />
      <p role="status" className="sr-only">
        {Math.min(shown, rows.length)} of {rows.length} tenants shown
      </p>
      {rows.length > shown && (
        <Button variant="secondary" className="self-start" onClick={() => setShown(shown + PAGE)}>
          Show more
        </Button>
      )}
      <Create />
    </div>
  );
}

/**
 * A new tenant, and its owner by email. Supabase Auth invites the owner if they have no account,
 * or finds them if they do, and grantr creates the tenant with them as its owner. It is confirmed
 * first, sent once, and the email is kept nowhere: not in the cache, not in the address, and not
 * once it is created.
 */
function Create() {
  const { commands, user } = Route.useRouteContext();
  const queryClient = useQueryClient();
  const heading = useId();
  const [tenant, setTenant] = useState("");
  const [email, setEmail] = useState("");
  const [made, setMade] = useState<string | null>(null);
  const field = useRef<HTMLInputElement>(null);
  const ready = isTenantId(tenant) && isEmail(email.trim());
  return (
    <Card
      render={<section aria-labelledby={heading} />}
      className="flex flex-col gap-3 sm:max-w-xl"
    >
      <SectionTitle id={heading}>Create a tenant</SectionTitle>
      <TextField
        ref={field}
        label="Tenant"
        name="tenant"
        autoComplete="off"
        spellCheck={false}
        value={tenant}
        onValueChange={(value) => {
          setMade(null);
          setTenant(String(value));
        }}
      />
      <TextField
        label="Owner's email"
        name="owner"
        type="email"
        autoComplete="off"
        value={email}
        onValueChange={(value) => {
          setMade(null);
          setEmail(String(value));
        }}
      />
      <ConfirmDialog
        label="Create tenant"
        className="self-start"
        title={`Create ${tenant.trim()}?`}
        confirm="Create the tenant"
        calm
        disabled={!ready}
        finalFocus={field}
        onConfirm={async () => {
          const created = orThrow(
            "Not created",
            await commands.portalr.createTenant(tenant.trim(), email.trim()),
          );
          setMade(`${created.tenant} is created, owned by ${created.owner}.`);
          setTenant("");
          setEmail("");
          await queryClient.invalidateQueries({ queryKey: keys.portalr.tenants(user) });
        }}
      >
        <p>
          Creates the tenant {tenant.trim()} and makes {email.trim()} its first owner. If they have
          no account, Supabase Auth sends them an invitation; if they have, they are found, and
          nothing is sent. A tenant can't be deleted from here.
        </p>
      </ConfirmDialog>
      {made && <Alert tone="info">{made}</Alert>}
    </Card>
  );
}
