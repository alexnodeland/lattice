import { outline } from "@portalr/client";
import { EmptyState, PageHeader, type Said, TextLink, TraceView } from "@portalr/ui";
import { useQuery, useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute, type ErrorComponentProps, Link } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { opening } from "../../../../../access";
import { ReadFailed } from "../../../../../read-failed";

const HEADER = <PageHeader title="Trace" />;

/**
 * One trace of a tenant's, for whoever may read its telemetry: its spans as a tree beside a
 * waterfall, and the chosen span's details. What was said in a span, its prompt and completion,
 * is read apart, when a span asks for it (portalr ADR-0030).
 */
export const Route = createFileRoute("/_signed/t/$tenant/traces/$trace")({
  head: ({ params }) => ({ meta: [{ title: `Trace · ${params.tenant} · portalr admin` }] }),
  beforeLoad: ({ context, params }) => opening(context, params.tenant, "portalr:read_telemetry"),
  loader: ({ context, params }) =>
    context.queryClient.ensureQueryData(context.queries.portalr.trace(params.tenant, params.trace)),
  component: TracePage,
  notFoundComponent: () => (
    <>
      {HEADER}
      <EmptyState title="Traces aren't yours to read here">
        portalr shows a tenant's traces to those who may read its telemetry, such as its owners and
        admins.
      </EmptyState>
    </>
  ),
  errorComponent: ({ error, reset }: ErrorComponentProps) => (
    <ReadFailed title="The trace couldn't be read" header={HEADER} error={error} reset={reset} />
  ),
});

function TracePage() {
  const { tenant, trace } = Route.useParams();
  const { queries } = Route.useRouteContext();
  const { data: reading } = useSuspenseQuery(queries.portalr.trace(tenant, trace));
  // What was said is read only once a span asks: a read of its own, kept apart.
  const [asked, setAsked] = useState(false);
  const spoken = useQuery({ ...queries.portalr.trace(tenant, trace, true), enabled: asked });
  const base = reading.status === "ok" ? reading.data : null;
  const full = asked && spoken.data?.status === "ok" ? spoken.data.data : null;
  const traced = full ?? base;
  const laid = useMemo(() => (traced === null ? null : outline(traced)), [traced]);
  let standing: Said = "hidden";
  if (asked) {
    standing = full ? "read" : spoken.isPending ? "reading" : "failed";
  }
  const header = (
    <PageHeader
      title="Trace"
      crumb={
        <TextLink render={<Link to="/t/$tenant/traces" params={{ tenant }} />}>Traces</TextLink>
      }
      meta={trace}
    />
  );
  if (reading.status === "unconfigured") {
    return (
      <>
        {header}
        <EmptyState title="Tempo isn't configured">
          Traces are read from Tempo, which this deployment runs without.
        </EmptyState>
      </>
    );
  }
  if (reading.status === "unavailable") {
    return (
      <>
        {header}
        <EmptyState title="Tempo isn't answering">
          <p role="alert">{reading.reason}</p>
        </EmptyState>
      </>
    );
  }
  if (laid === null) {
    return (
      <>
        {header}
        <EmptyState title="No such trace">
          Tempo has no trace by this id for this tenant: it may be older than Tempo keeps, or it
          isn't yours.
        </EmptyState>
      </>
    );
  }
  return (
    <div className="flex flex-col gap-6">
      {header}
      <TraceView outline={laid} said={standing} onAskToSee={() => setAsked(true)} />
    </div>
  );
}
