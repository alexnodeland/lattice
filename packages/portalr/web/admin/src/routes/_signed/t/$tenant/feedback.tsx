import type { PortalrApi } from "@portalr/client";
import {
  BarChart,
  DonutChart,
  EmptyState,
  ItemTable,
  LineChart,
  MAX_SERIES,
  Moment,
  PageHeader,
  SelectField,
  TextLink,
} from "@portalr/ui";
import { useQuery, useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute, type ErrorComponentProps } from "@tanstack/react-router";
import { useMemo } from "react";
import { opening } from "../../../../access";
import { type Shown, shownOf, WINDOWS, windowOf } from "../../../../feedback";
import { figure } from "../../../../home";
import { ReadFailed } from "../../../../read-failed";

type Summary = PortalrApi.components["schemas"]["Feedback"];
type Score = PortalrApi.components["schemas"]["Score"];

const HEADER = <PageHeader title="Feedback" meta="What people and evaluators said of the agent" />;

/** A mean as people read it: two places. */
const mean = (value: number) => value.toFixed(2);

/** A day as an axis reads it: `10-13`. */
const short = (day: string) => day.slice(5);

/** Where a trace is in no workspace. */
const NOWHERE = "In no workspace";

/**
 * A tenant's feedback and evaluations from Langfuse, for whoever may read its telemetry, summed
 * by day by portalr from every score in the window: people's thumbs per day, each evaluation's
 * mean per day, each workspace's share, and what people said, with Langfuse's page for each for
 * operators. The window and a workspace are in the address, so a view can be linked to (portalr
 * ADR-0027).
 */
export const Route = createFileRoute("/_signed/t/$tenant/feedback")({
  head: ({ params }) => ({ meta: [{ title: `Feedback · ${params.tenant} · portalr admin` }] }),
  validateSearch: (search: Record<string, unknown>): Shown => shownOf(search),
  beforeLoad: ({ context, params }) => opening(context, params.tenant, "portalr:read_telemetry"),
  loaderDeps: ({ search }) => search,
  loader: ({ context, params, deps }) => {
    // The router types a search of optional keys as `{}`: read it again, as the route keeps it.
    const { days, workspace } = shownOf(deps);
    return context.queryClient.ensureQueryData(
      context.queries.portalr.feedback(
        params.tenant,
        windowOf(days, new Date()),
        workspace ?? null,
      ),
    );
  },
  component: Feedback,
  notFoundComponent: () => (
    <>
      {HEADER}
      <EmptyState title="Feedback isn't yours to read here">
        portalr shows a tenant's feedback to those who may read its telemetry, such as its owners
        and admins.
      </EmptyState>
    </>
  ),
  errorComponent: ({ error, reset }: ErrorComponentProps) => (
    <ReadFailed title="Feedback couldn't be read" header={HEADER} error={error} reset={reset} />
  ),
});

function Feedback() {
  const { tenant } = Route.useParams();
  const shown = Route.useSearch();
  const { queries } = Route.useRouteContext();
  const days = shown.days ?? WINDOWS[0];
  const window = useMemo(() => windowOf(days, new Date()), [days]);
  const { data: reading } = useSuspenseQuery(
    queries.portalr.feedback(tenant, window, shown.workspace ?? null),
  );
  if (reading.status === "unconfigured") {
    return (
      <>
        {HEADER}
        <EmptyState title="Langfuse isn't configured">
          Feedback and evaluations are read from Langfuse, which this deployment runs without.
        </EmptyState>
      </>
    );
  }
  if (reading.status === "unavailable") {
    return (
      <>
        {HEADER}
        <EmptyState title="Langfuse isn't answering">
          <p role="alert">{reading.reason}</p>
        </EmptyState>
      </>
    );
  }
  const summary = reading.data;
  return (
    <div className="flex flex-col gap-6">
      {HEADER}
      <Filter
        shown={shown}
        workspaces={summary.workspaces.flatMap((place) => place.workspace ?? [])}
      />
      {!summary.complete && (
        <p role="status" className="text-muted text-sm">
          Langfuse holds more scores in this window than one read takes: these are sums of those
          read. Choose a shorter window, or a workspace, to see them all.
        </p>
      )}
      <Charts summary={summary} everywhere={shown.workspace === undefined} />
      <Comments comments={summary.comments} />
    </div>
  );
}

/** The thumbs per day, each evaluation's mean per day, and, for every workspace, each one's share. */
function Charts({ summary, everywhere }: { summary: Summary; everywhere: boolean }) {
  const drawn = summary.evaluations.slice(0, MAX_SERIES);
  const named = (evaluation: Summary["evaluations"][number]) =>
    `${evaluation.evaluator} · ${evaluation.name}`;
  const thumbed = summary.workspaces.filter((place) => place.up + place.down > 0);
  return (
    <>
      <BarChart
        label="People's thumbs per day"
        index={{ key: "day", name: "Day" }}
        series={[
          { key: "up", name: "Thumbs up" },
          { key: "down", name: "Thumbs down" },
        ]}
        data={summary.days.map((day) => ({ day: short(day.day), up: day.up, down: day.down }))}
        diverging
      />
      {drawn.length > 0 ? (
        <LineChart
          label="Each evaluation's mean per day"
          index={{ key: "day", name: "Day" }}
          series={drawn.map((evaluation) => ({ key: named(evaluation), name: named(evaluation) }))}
          data={summary.days.map((day, at) =>
            Object.fromEntries([
              ["day", short(day.day)],
              ...drawn.map((evaluation) => [named(evaluation), evaluation.days[at]?.mean ?? null]),
            ]),
          )}
          format={mean}
        />
      ) : (
        <EmptyState title="No evaluations in this window">
          An evaluator's numeric or yes-or-no scores are averaged here, each day.
        </EmptyState>
      )}
      {summary.evaluations.length > MAX_SERIES && (
        <ItemTable
          caption="Every evaluation"
          columns={[
            { key: "name", label: "Evaluation", cell: named },
            { key: "count", label: "Scores", cell: (evaluation) => figure(evaluation.count) },
          ]}
          items={summary.evaluations}
          keyOf={named}
          empty={{ title: "No evaluations", body: "None in this window." }}
        />
      )}
      {everywhere && thumbed.length > 0 && (
        <DonutChart
          label="People's thumbs by workspace"
          parts={thumbed.map((place) => ({
            name: place.workspace ?? NOWHERE,
            value: place.up + place.down,
          }))}
          format={figure}
        />
      )}
      {everywhere && (
        <ItemTable
          caption="By workspace"
          columns={[
            { key: "workspace", label: "Workspace", cell: (place) => place.workspace ?? NOWHERE },
            { key: "up", label: "Thumbs up", cell: (place) => figure(place.up) },
            { key: "down", label: "Thumbs down", cell: (place) => figure(place.down) },
            { key: "evaluated", label: "Evaluations", cell: (place) => figure(place.evaluated) },
          ]}
          items={summary.workspaces}
          keyOf={(place) => place.workspace ?? "~none"}
          empty={{ title: "No feedback yet", body: "Thumbs and evaluations appear here." }}
        />
      )}
    </>
  );
}

/** What people wrote beside a thumb, newest first, each with its trace, and, for operators, Langfuse's page. */
function Comments({ comments }: { comments: readonly Score[] }) {
  const { queries, user } = Route.useRouteContext();
  // An operator reads every tenant; the switch reads this too, so it is cached.
  const { data: every } = useQuery(queries.portalr.tenants(user));
  const operator = every !== null && every !== undefined;
  return (
    <ItemTable
      caption="What people said"
      columns={[
        { key: "comment", label: "Comment", cell: (score) => score.comment },
        {
          key: "thumb",
          label: "Thumb",
          cell: (score) => (score.value === true ? "Up" : score.value === false ? "Down" : "–"),
        },
        { key: "workspace", label: "Workspace", cell: (score) => score.workspace ?? "–" },
        { key: "at", label: "When", cell: (score) => <Moment at={score.timestamp} /> },
        {
          key: "trace",
          label: "Trace",
          cell: (score) =>
            operator ? (
              <InLangfuse trace={score.trace_id} />
            ) : (
              <code className="font-mono text-xs">{score.trace_id}</code>
            ),
        },
      ]}
      items={comments}
      keyOf={(score) => score.id}
      empty={{ title: "No comments yet", body: "What people write beside a thumb is shown here." }}
    />
  );
}

/** A trace's id, as a link to its page in Langfuse, which only an operator may follow. */
function InLangfuse({ trace }: { trace: string }) {
  const { queries, user } = Route.useRouteContext();
  const { data: links } = useQuery(queries.portalr.links(user, trace));
  const id = <code className="font-mono text-xs">{trace}</code>;
  return links?.langfuse_trace ? (
    <TextLink href={links.langfuse_trace} target="_blank" rel="noreferrer">
      {id}
    </TextLink>
  ) : (
    id
  );
}

/** The window, and a workspace, or every one: choosing either puts it in the address. */
function Filter({ shown, workspaces }: { shown: Shown; workspaces: readonly string[] }) {
  const navigate = Route.useNavigate();
  const go = (next: Partial<Record<keyof Shown, string>>) =>
    void navigate({ search: shownOf({ ...shown, ...next }) });
  const offered = [...new Set([...workspaces, ...(shown.workspace ? [shown.workspace] : [])])];
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <SelectField
        label="Window"
        value={String(shown.days ?? WINDOWS[0])}
        onChange={(event) => go({ days: event.target.value })}
        options={WINDOWS.map((days) => ({ value: String(days), label: `The last ${days} days` }))}
      />
      <SelectField
        label="Workspace"
        value={shown.workspace ?? ""}
        onChange={(event) => go({ workspace: event.target.value })}
        options={[
          { value: "", label: "Every workspace" },
          ...offered.sort().map((workspace) => ({ value: workspace, label: workspace })),
        ]}
      />
    </div>
  );
}
