import { outline, said, type Trace, wholeTrace } from "@portalr/client";
import {
  CRUMB,
  EmptyState,
  PageHeader,
  type Reveal,
  type Standing,
  TextLink,
  TraceView,
} from "@portalr/ui";
import { useQueries, useQuery, useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute, type ErrorComponentProps, Link } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { opening } from "../../../../../access";
import { ReadFailed } from "../../../../../read-failed";
import { analyticsSessionOf, isId } from "../../../../../traces";
import { Unanswered } from "../../../../../unanswered";

const HEADER = <PageHeader title="Trace" />;

/**
 * One trace of a tenant's, for whoever may read its telemetry: its spans as a tree beside a
 * waterfall, and the chosen span's details. What a span withheld, a prompt and a completion among
 * it, is read for that span alone, when it asks, and let go (portalr ADR-0030).
 */
export const Route = createFileRoute("/_signed/t/$tenant/traces/$trace")({
  head: ({ params, match }) => ({
    meta: [{ title: match.context.title(`Trace · ${params.tenant}`) }],
  }),
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
      <EmptyState focus title="Traces aren't yours to read here">
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
      breadcrumbs={[
        {
          label: "Traces",
          render: <Link to="/t/$tenant/traces" params={{ tenant }} activeOptions={CRUMB} />,
        },
      ]}
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
          <Unanswered tool="Tempo" reason={reading.reason} />
        </>
      );
    default:
      return (
        <>
          {header}
          {reading.data && <Session tenant={tenant} trace={reading.data} />}
          {laid ? <TraceView outline={laid} reveal={reveal} /> : <NoSuch />}
        </>
      );
  }
}

/**
 * The trace's analytics session, where a request of it carried one, and the session's traces:
 * for operators alone, as portalr gives the session to no one else (portalr ADR-0073).
 */
function Session({ tenant, trace }: { tenant: string; trace: Trace }) {
  const { queries, user } = Route.useRouteContext();
  // Whether they operate the deployment, as the tenant's frame reads it.
  const { data: every } = useQuery(queries.portalr.tenants(user));
  const session = analyticsSessionOf(trace.spans);
  if (session === undefined || every === null || every === undefined) {
    return null;
  }
  return (
    <p className="text-muted text-sm">
      Analytics session:{" "}
      <TextLink
        render={
          <Link
            to="/t/$tenant/traces"
            params={{ tenant }}
            search={{ hours: 168, analytics: session }}
          />
        }
      >
        <code className="font-mono">{session}</code>
      </TextLink>
    </p>
  );
}

/** A span of a trace, by its id. */
function spanOf(trace: Trace | null | undefined, id: string) {
  return trace?.spans.find((span) => span.span_id === id);
}
