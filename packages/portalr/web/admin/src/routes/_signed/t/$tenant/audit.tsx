import type { AuditFilter } from "@portalr/client";
import {
  Button,
  Card,
  EmptyState,
  ItemTable,
  PageHeader,
  SectionTitle,
  SelectField,
  TextField,
} from "@portalr/ui";
import { useSuspenseInfiniteQuery } from "@tanstack/react-query";
import { createFileRoute, type ErrorComponentProps, useRouter } from "@tanstack/react-router";
import { type FormEvent, useId, useState } from "react";
import { opening } from "../../../../access";
import { actor, filterOf, MAKERS, said, TYPES } from "../../../../audit";

const HEADER = <PageHeader title="Audit" meta="Every change to who may see and do what" />;

/**
 * A tenant's audit log, for whoever may read it: each change, who made it, and when, the newest
 * first, a page at a time, filtered by one type of change and one maker, which the address keeps, so
 * a filtered log can be linked to. grantr filters it (grantr ADR-0030, ADR-0032; portalr ADR-0026).
 */
export const Route = createFileRoute("/_signed/t/$tenant/audit")({
  head: ({ params }) => ({ meta: [{ title: `Audit · ${params.tenant} · portalr admin` }] }),
  validateSearch: (search: Record<string, unknown>): AuditFilter => filterOf(search),
  beforeLoad: ({ context, params }) => opening(context, params.tenant, "grantr:read_audit"),
  loaderDeps: ({ search }) => search,
  loader: ({ context, params, deps }) =>
    context.queryClient.ensureInfiniteQueryData(context.queries.grantr.audit(params.tenant, deps)),
  component: Audit,
  notFoundComponent: () => (
    <>
      {HEADER}
      <EmptyState title="The audit log isn't yours to read here">
        grantr shows a tenant's audit log to those who may read it, such as its owners.
      </EmptyState>
    </>
  ),
  errorComponent: Failed,
});

function Audit() {
  const { tenant } = Route.useParams();
  const filter = Route.useSearch();
  const { queries } = Route.useRouteContext();
  const { data, hasNextPage, fetchNextPage, isFetchingNextPage } = useSuspenseInfiniteQuery(
    queries.grantr.audit(tenant, filter),
  );
  const entries = data.pages.flat();
  const filtered = Object.keys(filter).length > 0;
  return (
    <div className="flex flex-col gap-6">
      {HEADER}
      <Filter key={JSON.stringify(filter)} filter={filter} />
      <ItemTable
        caption="Audit log"
        columns={[
          { key: "change", label: "Change", cell: (entry) => said(entry.event) },
          { key: "by", label: "By", cell: (entry) => actor(entry.by) },
          {
            key: "at",
            label: "When",
            cell: (entry) => <time dateTime={entry.at}>{new Date(entry.at).toLocaleString()}</time>,
          },
        ]}
        items={entries}
        keyOf={(entry) => String(entry.seq)}
        empty={
          filtered
            ? { title: "No changes match", body: "Change the filter, or clear it." }
            : { title: "No changes yet", body: "Each change to access in the tenant is kept here." }
        }
      />
      {hasNextPage && (
        <Button
          variant="secondary"
          className="self-start"
          aria-busy={isFetchingNextPage}
          disabled={isFetchingNextPage}
          onClick={() => void fetchNextPage()}
        >
          Show more
        </Button>
      )}
    </div>
  );
}

/**
 * The filter: one type of change, or any, and who made it, by their kind and id, and a rule's
 * workspace. Applying it puts it in the address.
 */
function Filter({ filter }: { filter: AuditFilter }) {
  const navigate = Route.useNavigate();
  const heading = useId();
  const [kind, setKind] = useState<string>(filter.actor_kind ?? "");
  function apply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void navigate({ search: filterOf(Object.fromEntries(new FormData(event.currentTarget))) });
  }
  return (
    <Card render={<section aria-labelledby={heading} />} className="flex flex-col gap-3">
      <SectionTitle id={heading}>Filter</SectionTitle>
      <form className="grid gap-3 sm:grid-cols-2" onSubmit={apply}>
        <SelectField
          label="Change"
          name="type"
          defaultValue={filter.type ?? ""}
          options={[{ value: "", label: "Any change" }, ...TYPES]}
        />
        <SelectField
          label="Made by"
          name="actor_kind"
          value={kind}
          onChange={(event) => setKind(event.target.value)}
          options={MAKERS}
        />
        {(kind === "user" || kind === "service_principal" || kind === "rule") && (
          <TextField
            label={kind === "rule" ? "The rule's name" : "Their id"}
            name="actor"
            defaultValue={filter.actor ?? ""}
            autoComplete="off"
            spellCheck={false}
            required
          />
        )}
        {kind === "rule" && (
          <TextField
            label="The rule's workspace"
            name="workspace"
            defaultValue={filter.workspace ?? ""}
            autoComplete="off"
            required
          />
        )}
        <div className="flex flex-wrap gap-2 sm:col-span-2">
          <Button type="submit">Apply</Button>
          <Button variant="secondary" onClick={() => void navigate({ search: {} })}>
            Clear
          </Button>
        </div>
      </form>
    </Card>
  );
}

/** The log's read failed: what failed, and a way to read it again. */
function Failed({ error, reset }: ErrorComponentProps) {
  const router = useRouter();
  return (
    <>
      {HEADER}
      <EmptyState
        title="The audit log couldn't be read"
        action={
          <Button
            variant="secondary"
            onClick={() => {
              reset();
              void router.invalidate();
            }}
          >
            Try again
          </Button>
        }
      >
        <p role="alert">{error instanceof Error ? error.message : String(error)}</p>
      </EmptyState>
    </>
  );
}
