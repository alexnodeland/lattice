import { LOGS_LIMIT, type PortalrApi } from "@portalr/client";
import {
  Button,
  Card,
  EmptyState,
  type LineReveal,
  LogList,
  PageHeader,
  SectionTitle,
  SelectField,
  TextField,
} from "@portalr/ui";
import { useQueries, useSuspenseQueries } from "@tanstack/react-query";
import {
  createFileRoute,
  type ErrorComponentProps,
  type SearchSchemaInput,
} from "@tanstack/react-router";
import { type FormEvent, useId, useState } from "react";
import { opening } from "../../../../access";
import { Health } from "../../../../health";
import { healthWindow, LOG_RANGES, logWindow, type Shown, shownOf } from "../../../../logs";
import { ReadFailed } from "../../../../read-failed";
import { ID_PATTERN } from "../../../../traces";

const HEADER = <PageHeader title="Logs" meta="What the application wrote, and how it is doing" />;

/**
 * A tenant's logs from Loki, and its health from Prometheus, for whoever may read its telemetry.
 * A record is listed with its time, level, service, thread and run, and the length of its line:
 * the line itself is asked for, one record's at a time (portalr ADR-0031). The windows and the
 * filters are in the address, so a view can be linked to.
 */
export const Route = createFileRoute("/_signed/t/$tenant/logs")({
  head: ({ params }) => ({ meta: [{ title: `Logs · ${params.tenant} · portalr admin` }] }),
  // What a link may give, each of it optional; what the address gives, read with `shownOf`.
  validateSearch: (search: Shown & SearchSchemaInput): Required<Shown> => shownOf(search),
  beforeLoad: ({ context, params }) => opening(context, params.tenant, "portalr:read_telemetry"),
  // The windows, worked out once, to the minute it is: the same for a minute.
  loaderDeps: ({ search }: { search: Required<Shown> }) => ({
    logs: logWindow(search.hours, new Date()),
    health: healthWindow(search.health, new Date()),
    thread: search.thread,
    run: search.run,
  }),
  loader: async ({ context, params, deps }) => {
    const { queries, queryClient } = context;
    await Promise.all([
      queryClient.ensureQueryData(
        queries.portalr.logs(params.tenant, deps.logs, { thread: deps.thread, run: deps.run }),
      ),
      queryClient.ensureQueryData(
        queries.portalr.metrics(params.tenant, "turn_latency", deps.health),
      ),
      queryClient.ensureQueryData(
        queries.portalr.metrics(params.tenant, "failed_turns", deps.health),
      ),
    ]);
  },
  component: LogsPage,
  notFoundComponent: () => (
    <>
      {HEADER}
      <EmptyState title="Logs aren't yours to read here">
        portalr shows a tenant's logs to those who may read its telemetry, such as its owners and
        admins.
      </EmptyState>
    </>
  ),
  errorComponent: ({ error, reset }: ErrorComponentProps) => (
    <ReadFailed title="Logs couldn't be read" header={HEADER} error={error} reset={reset} />
  ),
});

/** The page, for the windows and filters the address names: another is another page. */
function LogsPage() {
  const shown = Route.useSearch();
  return <Body key={JSON.stringify(shown)} shown={shown} />;
}

function Body({ shown }: { shown: Required<Shown> }) {
  const { tenant } = Route.useParams();
  const deps = Route.useLoaderDeps();
  const navigate = Route.useNavigate();
  const { queries } = Route.useRouteContext();
  const [logs, latency, failures] = useSuspenseQueries({
    queries: [
      queries.portalr.logs(tenant, deps.logs, { thread: deps.thread, run: deps.run }),
      queries.portalr.metrics(tenant, "turn_latency", deps.health),
      queries.portalr.metrics(tenant, "failed_turns", deps.health),
    ],
  });
  // The records that asked to see their line, each read for itself, and let go with the page.
  const [asked, setAsked] = useState<readonly string[]>([]);
  const reads = useQueries({ queries: asked.map((id) => queries.portalr.logLine(tenant, id)) });
  const reveal: LineReveal = {
    standing(id) {
      const read = reads[asked.indexOf(id)];
      if (!read) {
        return "hidden";
      }
      if (read.isPending) {
        return "reading";
      }
      return read.data?.status === "ok" ? "read" : "failed";
    },
    line(id) {
      const read = reads[asked.indexOf(id)]?.data;
      return read?.status === "ok" ? (read.data?.line ?? null) : null;
    },
    ask: (id) => setAsked((before) => (before.includes(id) ? before : [...before, id])),
  };
  return (
    <div className="flex flex-col gap-8">
      {HEADER}
      <Health
        window={deps.health}
        hours={shown.health}
        latency={latency.data}
        failures={failures.data}
        onWindow={(hours) => void navigate({ search: shownOf({ ...shown, health: hours }) })}
      />
      <section aria-labelledby="records" className="flex flex-col gap-4">
        <SectionTitle id="records">Logs</SectionTitle>
        <Filter shown={shown} />
        <Records
          reading={logs.data}
          reveal={reveal}
          filtered={shown.thread !== undefined || shown.run !== undefined}
        />
      </section>
    </div>
  );
}

type Reading = PortalrApi.components["schemas"]["Ok_Logs_"] | Unread;
type Unread =
  | PortalrApi.components["schemas"]["Unavailable"]
  | PortalrApi.components["schemas"]["Unconfigured"];

/** The records, or why there are none: Loki isn't there, isn't answering, or has none. */
function Records({
  reading,
  reveal,
  filtered,
}: {
  reading: Reading;
  reveal: LineReveal;
  filtered: boolean;
}) {
  switch (reading.status) {
    case "unconfigured":
      return (
        <EmptyState title="Loki isn't configured">
          Logs are read from Loki, which this deployment runs without.
        </EmptyState>
      );
    case "unavailable":
      return (
        <EmptyState title="Loki isn't answering">
          <p role="alert">{reading.reason}</p>
        </EmptyState>
      );
    case "ok":
      return reading.data.records.length === 0 ? (
        <EmptyState title={filtered ? "No records match" : "No log records in this window"}>
          {filtered
            ? "Widen the window, or clear the thread or run."
            : "Whatever the application writes is shown here, newest first."}
        </EmptyState>
      ) : (
        <LogList records={reading.data.records} complete={reading.data.complete} reveal={reveal} />
      );
  }
}

/** The logs' window, and a thread's or a run's id: applying them puts them in the address. */
function Filter({ shown }: { shown: Required<Shown> }) {
  const navigate = Route.useNavigate();
  const heading = useId();
  function apply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = Object.fromEntries(new FormData(event.currentTarget));
    void navigate({ search: shownOf({ ...form, health: shown.health }) });
  }
  return (
    <Card render={<section aria-labelledby={heading} />} className="flex flex-col gap-3">
      <SectionTitle id={heading}>Find</SectionTitle>
      <form className="grid gap-3 sm:grid-cols-3" onSubmit={apply}>
        <SelectField
          label="Window"
          name="hours"
          defaultValue={String(shown.hours)}
          options={LOG_RANGES.map((range) => ({ value: String(range.hours), label: range.label }))}
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
              void navigate({
                search: {
                  hours: shown.hours,
                  health: shown.health,
                  thread: undefined,
                  run: undefined,
                },
              })
            }
          >
            Clear
          </Button>
        </div>
      </form>
      <p className="text-muted text-xs">
        The newest {LOGS_LIMIT} records of a window of a day at most are read.
      </p>
    </Card>
  );
}
