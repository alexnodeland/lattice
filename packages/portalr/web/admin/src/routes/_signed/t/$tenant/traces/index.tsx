import { TRACES_LIMIT } from "@portalr/client";
import {
  Button,
  Card,
  duration,
  EmptyState,
  ItemTable,
  Moment,
  PageHeader,
  SectionTitle,
  SelectField,
  TextField,
  TextLink,
} from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import {
  createFileRoute,
  type ErrorComponentProps,
  Link,
  type SearchSchemaInput,
} from "@tanstack/react-router";
import { type FormEvent, useId } from "react";
import { opening } from "../../../../../access";
import { ReadFailed } from "../../../../../read-failed";
import {
  ID_PATTERN,
  RANGES,
  type Shown,
  shownOf,
  startedAt,
  windowOf,
} from "../../../../../traces";

const HEADER = <PageHeader title="Traces" meta="What the agents did, step by step" />;

/**
 * A tenant's traces from Tempo, for whoever may read its telemetry: the newest first, in the last
 * hour, day or week, or a thread's or a run's. Each opens its spans as a tree and a waterfall. The
 * window and the filters are in the address, so a view can be linked to (portalr ADR-0030).
 */
export const Route = createFileRoute("/_signed/t/$tenant/traces/")({
  head: ({ params }) => ({ meta: [{ title: `Traces · ${params.tenant} · portalr admin` }] }),
  // What a link may give, each of it optional; what the address gives, read with `shownOf`.
  validateSearch: (search: Shown & SearchSchemaInput): Required<Shown> => shownOf(search),
  beforeLoad: ({ context, params }) => opening(context, params.tenant, "portalr:read_telemetry"),
  // The window, worked out once, to the minute it is: the same for a minute.
  loaderDeps: ({ search }: { search: Required<Shown> }) => ({
    window: windowOf(search.hours, new Date()),
    session: search.thread,
    run: search.run,
  }),
  loader: ({ context, params, deps }) =>
    context.queryClient.ensureQueryData(
      context.queries.portalr.traces(params.tenant, deps.window, {
        session: deps.session,
        run: deps.run,
      }),
    ),
  component: Traces,
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
    <ReadFailed title="Traces couldn't be read" header={HEADER} error={error} reset={reset} />
  ),
});

function Traces() {
  const { tenant } = Route.useParams();
  const shown = Route.useSearch();
  const { window, session, run } = Route.useLoaderDeps();
  const { queries } = Route.useRouteContext();
  const { data: reading } = useSuspenseQuery(
    queries.portalr.traces(tenant, window, { session, run }),
  );
  if (reading.status === "unconfigured") {
    return (
      <>
        {HEADER}
        <EmptyState title="Tempo isn't configured">
          Traces are read from Tempo, which this deployment runs without.
        </EmptyState>
      </>
    );
  }
  if (reading.status === "unavailable") {
    return (
      <>
        {HEADER}
        <EmptyState title="Tempo isn't answering">
          <p role="alert">{reading.reason}</p>
        </EmptyState>
      </>
    );
  }
  const traces = reading.data;
  const filtered = shown.thread !== undefined || shown.run !== undefined;
  return (
    <div className="flex flex-col gap-6">
      {HEADER}
      {/* Keyed by what the address holds, so the form's own fields start from it again when it changes. */}
      <Filter key={JSON.stringify(shown)} shown={shown} />
      {traces.length >= TRACES_LIMIT && (
        <p role="status" className="text-muted text-sm">
          The newest {TRACES_LIMIT} are shown. A shorter window, or a thread or a run, finds the
          rest.
        </p>
      )}
      <ItemTable
        caption="Traces"
        columns={[
          {
            key: "trace",
            label: "Trace",
            cell: (trace) => (
              <TextLink
                render={
                  <Link to="/t/$tenant/traces/$trace" params={{ tenant, trace: trace.trace_id }} />
                }
              >
                <code className="font-mono text-xs">{trace.trace_id}</code>
              </TextLink>
            ),
          },
          {
            key: "at",
            label: "Began",
            cell: (trace) => <Moment at={startedAt(trace.start_ns)} />,
          },
          {
            key: "took",
            label: "Took",
            cell: (trace) => (trace.duration_ms == null ? "–" : duration(trace.duration_ms)),
          },
        ]}
        items={traces}
        keyOf={(trace) => trace.trace_id}
        empty={
          filtered
            ? { title: "No traces match", body: "Widen the window, or clear the thread or run." }
            : {
                title: "No traces in this window",
                body: "A trace is made each time the agent takes a turn or a rule runs.",
              }
        }
      />
    </div>
  );
}

/** The window, and a thread's or a run's id: applying them puts them in the address. */
function Filter({ shown }: { shown: Required<Shown> }) {
  const navigate = Route.useNavigate();
  const heading = useId();
  function apply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = Object.fromEntries(new FormData(event.currentTarget));
    void navigate({ search: shownOf(form) });
  }
  return (
    <Card render={<section aria-labelledby={heading} />} className="flex flex-col gap-3">
      <SectionTitle id={heading}>Find</SectionTitle>
      <form className="grid gap-3 sm:grid-cols-3" onSubmit={apply}>
        <SelectField
          label="Window"
          name="hours"
          defaultValue={String(shown.hours)}
          options={RANGES.map((range) => ({ value: String(range.hours), label: range.label }))}
        />
        <TextField
          label="Thread"
          name="thread"
          defaultValue={shown.thread ?? ""}
          autoComplete="off"
          spellCheck={false}
          pattern={`\\s*${ID_PATTERN}\\s*|`}
        />
        <TextField
          label="Run"
          name="run"
          defaultValue={shown.run ?? ""}
          autoComplete="off"
          spellCheck={false}
          pattern={`\\s*${ID_PATTERN}\\s*|`}
        />
        <div className="flex flex-wrap gap-2 sm:col-span-3">
          <Button type="submit">Apply</Button>
          <Button
            variant="secondary"
            onClick={() =>
              void navigate({ search: { hours: shown.hours, thread: undefined, run: undefined } })
            }
          >
            Clear
          </Button>
        </div>
      </form>
    </Card>
  );
}
