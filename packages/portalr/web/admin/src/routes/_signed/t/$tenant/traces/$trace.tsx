import { outline, said, type Trace, wholeTrace } from "@portalr/client";
import {
  EmptyState,
  PageHeader,
  type Reveal,
  type Standing,
  TextLink,
  TraceView,
} from "@portalr/ui";
import { useQueries, useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute, type ErrorComponentProps, Link } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { opening } from "../../../../../access";
import { ReadFailed } from "../../../../../read-failed";
import { isId } from "../../../../../traces";

const HEADER = <PageHeader title="Trace" />;

/**
 * One trace of a tenant's, for whoever may read its telemetry: its spans as a tree beside a
 * waterfall, and the chosen span's details. What a span withheld, a prompt and a completion among
 * it, is read for that span alone, when it asks, and let go (portalr ADR-0030).
 */
export const Route = createFileRoute("/_signed/t/$tenant/traces/$trace")({
  head: ({ params }) => ({ meta: [{ title: `Trace · ${params.tenant} · portalr admin` }] }),
  beforeLoad: ({ context, params }) => opening(context, params.tenant, "portalr:read_telemetry"),
  // An id portalr wouldn't take isn't read: there is no such trace.
  loader: async ({ context, params }) => {
    if (isId(params.trace)) {
      await context.queryClient.ensureQueryData(
        context.queries.portalr.trace(params.tenant, params.trace),
      );
    }
  },
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

/** The page, for the tenant and the trace the address names: another of either is another page. */
function TracePage() {
  const { tenant, trace } = Route.useParams();
  if (!isId(trace)) {
    return (
      <>
        <PageHeader title="Trace" meta={trace} />
        <NoSuch />
      </>
    );
  }
  return <Body key={`${tenant}:${wholeTrace(trace)}`} trace={trace} />;
}

const NoSuch = () => (
  <EmptyState title="No such trace">
    Tempo has no trace by this id for this tenant: it may be older than Tempo keeps, or it isn't
    yours.
  </EmptyState>
);

function Body({ trace }: { trace: string }) {
  const { tenant } = Route.useParams();
  const { queries } = Route.useRouteContext();
  const { data: reading } = useSuspenseQuery(queries.portalr.trace(tenant, trace));
  // The spans that asked to see what they withheld, each read for itself, and let go with the page.
  const [asked, setAsked] = useState<readonly string[]>([]);
  const reads = useQueries({
    queries: asked.map((span) => queries.portalr.trace(tenant, trace, span)),
  });
  const header = (
    <PageHeader
      title="Trace"
      crumb={
        <TextLink render={<Link to="/t/$tenant/traces" params={{ tenant }} />}>Traces</TextLink>
      }
      meta={trace}
    />
  );
  const laid = useMemo(
    () => (reading.status === "ok" && reading.data ? outline(reading.data) : null),
    [reading],
  );
  const reveal: Reveal = {
    standing(id): Standing {
      const read = reads[asked.indexOf(id)];
      if (!read) {
        return "hidden";
      }
      if (read.isPending) {
        return "reading";
      }
      return read.data?.status === "ok" && read.data.data ? "read" : "failed";
    },
    parts(row) {
      const read = reads[asked.indexOf(row.id)]?.data;
      const span = read?.status === "ok" ? spanOf(read.data, row.id) : undefined;
      return span ? said(span.attributes, row.withheld) : [];
    },
    ask: (id) => setAsked((before) => (before.includes(id) ? before : [...before, id])),
  };
  switch (reading.status) {
    case "unconfigured":
      return (
        <>
          {header}
          <EmptyState title="Tempo isn't configured">
            Traces are read from Tempo, which this deployment runs without.
          </EmptyState>
        </>
      );
    case "unavailable":
      return (
        <>
          {header}
          <EmptyState title="Tempo isn't answering">
            <p role="alert">{reading.reason}</p>
          </EmptyState>
        </>
      );
    default:
      return (
        <>
          {header}
          {laid ? <TraceView outline={laid} reveal={reveal} /> : <NoSuch />}
        </>
      );
  }
}

/** A span of a trace, by its id. */
function spanOf(trace: Trace | null | undefined, id: string) {
  return trace?.spans.find((span) => span.span_id === id);
}
