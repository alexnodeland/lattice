import { usePeople } from "@portalr/client";
import { Button, ItemTable, Moment, PageHeader } from "@portalr/ui";
import { useSuspenseInfiniteQuery } from "@tanstack/react-query";
import { createFileRoute, type ErrorComponentProps } from "@tanstack/react-router";
import { actor, peopleOf, said } from "../../../audit";
import { ReadFailed } from "../../../read-failed";

const HEADER = (
  <PageHeader title="Audit" meta="Who was made an operator, and who stopped being one" />
);

/**
 * The deployment's audit log, for its operators: each change to who may operate the deployment, who
 * made it, and when, the newest first, a page at a time (grantr's `GET /audit`, which needs
 * `grantr:grant_operator`). A tenant's own changes are in its Audit (portalr ADR-0034).
 */
export const Route = createFileRoute("/_signed/deployment/audit")({
  head: () => ({ meta: [{ title: "Audit · portalr admin" }] }),
  // The deployment's layout read who is an operator before letting anyone in.
  loader: ({ context }) =>
    context.queryClient.ensureInfiniteQueryData(
      context.queries.grantr.deploymentAudit(context.user),
    ),
  component: Audit,
  errorComponent: ({ error, reset }: ErrorComponentProps) => (
    <ReadFailed
      title="The deployment's audit log couldn't be read"
      header={HEADER}
      error={error}
      reset={reset}
    />
  ),
});

function Audit() {
  const { queries, user, config } = Route.useRouteContext();
  const { data, hasNextPage, fetchNextPage, isFetchingNextPage, isFetchNextPageError, error } =
    useSuspenseInfiniteQuery(queries.grantr.deploymentAudit(user));
  // Each page is oldest first, and each is older than the last: the newest are on top.
  const entries = data.pages.flatMap((page) => [...page].reverse());
  // An operator is shown anyone by email, in no tenant (portalr ADR-0035).
  const names = usePeople(queries, config.people, null, entries.flatMap(peopleOf));
  return (
    <div className="flex flex-col gap-6">
      {HEADER}
      <ItemTable
        caption="Deployment audit log"
        columns={[
          { key: "change", label: "Change", cell: (entry) => said(entry.event, names) },
          { key: "by", label: "By", cell: (entry) => actor(entry.by, names) },
          { key: "at", label: "When", cell: (entry) => <Moment at={entry.at} /> },
        ]}
        items={entries}
        keyOf={(entry) => String(entry.seq)}
        named={(entry) => `${said(entry.event, names)}, ${new Date(entry.at).toLocaleString()}`}
        empty={{
          title: "No changes yet",
          body: "Each time someone is made an operator, or stops being one, it is kept here.",
        }}
      />
      <p role="status" className="sr-only">
        {entries.length === 1 ? "1 change shown" : `${entries.length} changes shown`}
      </p>
      {isFetchNextPageError && (
        <p role="alert">
          The changes before these couldn't be read:{" "}
          {error instanceof Error ? error.message : String(error)}
        </p>
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
