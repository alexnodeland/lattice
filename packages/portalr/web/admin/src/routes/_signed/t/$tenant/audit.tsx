import type { AuditFilter } from "@portalr/client";
import {
  Alert,
  Button,
  Card,
  EmptyState,
  ItemTable,
  Moment,
  PageHeader,
  SectionTitle,
  SelectField,
  TextField,
} from "@portalr/ui";
import { useSuspenseInfiniteQuery } from "@tanstack/react-query";
import { createFileRoute, type ErrorComponentProps } from "@tanstack/react-router";
import { type FormEvent, useId, useState } from "react";
import { opening, useNames } from "../../../../access";
import {
  actor,
  filterOf,
  ID_FIELD,
  MAKERS,
  peopleOf,
  said,
  searchOf,
  TYPES,
} from "../../../../audit";
import { ReadFailed } from "../../../../read-failed";

const HEADER = <PageHeader title="Audit" meta="Every change to who may see and do what" />;

/**
 * A tenant's audit log, for whoever may read it: each change, who made it, and when, the newest
 * first, a page at a time, filtered by one type of change and one maker, which the address keeps, so
 * a filtered log can be linked to. grantr filters it (grantr ADR-0030, ADR-0032; portalr ADR-0026).
 */
export const Route = createFileRoute("/_signed/t/$tenant/audit")({
  head: ({ params }) => ({ meta: [{ title: `Audit · ${params.tenant} · portalr admin` }] }),
  validateSearch: searchOf,
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
  const { data, hasNextPage, fetchNextPage, isFetchingNextPage, isFetchNextPageError, error } =
    useSuspenseInfiniteQuery(queries.grantr.audit(tenant, filter));
  // Each page is oldest first, and each is older than the last: the newest are on top.
  const entries = data.pages.flatMap((page) => [...page].reverse());
  const filtered = Object.values(filter).some((value) => value !== undefined);
  const names = useNames(tenant, entries.flatMap(peopleOf));
  return (
    <div className="flex flex-col gap-6">
      {HEADER}
      <Filter key={JSON.stringify(filter)} filter={filter} />
      <ItemTable
        caption="Audit log"
        columns={[
          { key: "change", label: "Change", cell: (entry) => said(entry.event, names) },
          { key: "by", label: "By", cell: (entry) => actor(entry.by, names) },
          { key: "at", label: "When", cell: (entry) => <Moment at={entry.at} /> },
        ]}
        items={entries}
        keyOf={(entry) => String(entry.seq)}
        named={(entry) => `${said(entry.event, names)}, ${new Date(entry.at).toLocaleString()}`}
        empty={
          filtered
            ? { title: "No changes match", body: "Change the filter, or clear it." }
            : { title: "No changes yet", body: "Each change to access in the tenant is kept here." }
        }
      />
      {/* Each page read says how many are shown, so the reader hears it when Show more goes. */}
      <p role="status" className="sr-only">
        {entries.length === 1 ? "1 change shown" : `${entries.length} changes shown`}
      </p>
      {isFetchNextPageError && (
        <Alert tone="error">
          The changes before these couldn't be read:{" "}
          {error instanceof Error ? error.message : String(error)}
        </Alert>
      )}
      {hasNextPage && (
        <Button
          variant="secondary"
          className="self-start"
          aria-busy={isFetchingNextPage}
          disabled={isFetchingNextPage}
          focusableWhenDisabled
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
          onValueChange={setKind}
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
            // A person's or a service principal's id, as grantr takes one.
            {...(kind !== "rule" && { pattern: ID_FIELD })}
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

/** The log's read failed: what failed, a way to read it again, and to clear a filter grantr refused. */
function Failed({ error, reset }: ErrorComponentProps) {
  const filter = Route.useSearch();
  const navigate = Route.useNavigate();
  return (
    <ReadFailed title="The audit log couldn't be read" header={HEADER} error={error} reset={reset}>
      {Object.values(filter).some((value) => value !== undefined) && (
        <Button
          variant="secondary"
          onClick={() => {
            reset();
            void navigate({ search: {} });
          }}
        >
          Clear the filter
        </Button>
      )}
    </ReadFailed>
  );
}
