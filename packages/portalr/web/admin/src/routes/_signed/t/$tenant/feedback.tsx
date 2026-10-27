import type { PortalrApi } from "@portalr/client";
import {
  Alert,
  BarChart,
  DonutChart,
  EmptyState,
  formatDay,
  ItemTable,
  LineChart,
  MAX_SERIES,
  Moment,
  PageHeader,
  SegmentedFilter,
  SelectField,
  StatusBadge,
  TextLink,
} from "@portalr/ui";
import { useQuery, useSuspenseQuery } from "@tanstack/react-query";
import {
  createFileRoute,
  type ErrorComponentProps,
  Link,
  type SearchSchemaInput,
} from "@tanstack/react-router";
import { opening } from "../../../../access";
import { type Shown, shownOf, unknownDays } from "../../../../feedback";
import { figure } from "../../../../format";
import { ReadFailed } from "../../../../read-failed";
import { Unanswered } from "../../../../unanswered";
import { WINDOWS, windowOf } from "../../../../window";

type Summary = PortalrApi.components["schemas"]["Feedback"];
type Comment = PortalrApi.components["schemas"]["Comment"];
type Evaluation = Summary["evaluations"][number];

const HEADER = <PageHeader title="Feedback" meta="What people and evaluators said of the agent" />;

/** A mean as people read it: two places. */
const mean = (value: number) => value.toFixed(2);

/** What the axes and tables call a day: one in UTC, as portalr sums them. */
const DAY = { key: "day", name: "Day (UTC)" } as const;

/** Where a trace is in no workspace, and the key it is kept under, which no workspace has. */
const NOWHERE = { key: "~none", name: "In no workspace" } as const;

/** An evaluation's name, as its line and its row say it. */
const named = (evaluation: Evaluation) => `${evaluation.evaluator} · ${evaluation.name}`;

/**
 * The id the operators' Langfuse link is read for, once: each trace's link is it, with the
 * trace's own id in its place.
 */
const TEMPLATE = "portalr-trace";

/**
 * A tenant's feedback and evaluations from Langfuse, for whoever may read its telemetry, summed
 * by day, in UTC, by portalr: people's thumbs per day, each evaluation's mean per day, each
 * workspace's share, and what people said, with Langfuse's page for each for operators. The window
 * and a workspace are in the address, so a view can be linked to (portalr ADR-0027).
 */
export const Route = createFileRoute("/_signed/t/$tenant/feedback")({
  head: ({ params, match }) => ({
    meta: [{ title: match.context.title(`Feedback · ${params.tenant}`) }],
  }),
  // What a link may give, each of it optional; what the address gives, read with `shownOf`.
  validateSearch: (search: Shown & SearchSchemaInput): Required<Shown> => shownOf(search),
  beforeLoad: ({ context, params }) => opening(context, params.tenant, "portalr:read_telemetry"),
  // The window, worked out once, from the day it is: the same all day.
  loaderDeps: ({ search }: { search: Required<Shown> }) => ({
    window: windowOf(search.days, new Date()),
    workspace: search.workspace,
  }),
  loader: ({ context, params, deps }) =>
    context.queryClient.ensureQueryData(
      context.queries.portalr.feedback(params.tenant, deps.window, deps.workspace ?? null),
    ),
  component: Feedback,
  notFoundComponent: () => (
    <>
      {HEADER}
      <EmptyState focus title="Feedback isn't yours to read here">
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
  const { window, workspace } = Route.useLoaderDeps();
  const { queries } = Route.useRouteContext();
  const { data: reading } = useSuspenseQuery(
    queries.portalr.feedback(tenant, window, workspace ?? null),
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
        <Unanswered tool="Langfuse" reading={reading} />
      </>
    );
  }
  const summary = reading.data;
  return (
    <div className="flex flex-col gap-6">
      {HEADER}
      <Filter tenant={tenant} shown={shown} />
      {!summary.complete && (
        <Alert tone="warn">
          <StatusBadge tone="stopped" className="mr-2">
            Partial
          </StatusBadge>
          Some days, scores and comments may be missing. A shorter window, or one workspace, may
          read them all.
          {unknownDays(summary) > 0 &&
            " The shaded days weren't reached: they're unknown, not empty."}
        </Alert>
      )}
      <Charts summary={summary} everywhere={workspace === undefined} />
      <Comments comments={summary.comments} />
    </div>
  );
}

/** The thumbs per day, each evaluation's mean per day, and, for every workspace, each one's share. */
function Charts({ summary, everywhere }: { summary: Summary; everywhere: boolean }) {
  const drawn = summary.evaluations.slice(0, MAX_SERIES);
  const unknown = unknownDays(summary);
  /** A day's value, or none on a day the read didn't reach. */
  const known = (at: number, value: number | null) => (at < unknown ? null : value);
  const thumbed = summary.workspaces.filter((place) => place.up + place.down > 0);
  const thumbs = summary.days.some((day) => day.up + day.down > 0);
  return (
    <>
      {thumbs ? (
        <BarChart
          label="People's thumbs per day"
          index={DAY}
          series={[
            { key: "up", name: "Thumbs up" },
            { key: "down", name: "Thumbs down" },
          ]}
          data={summary.days.map((day, at) => ({
            day: day.day,
            up: known(at, day.up),
            down: known(at, day.down),
          }))}
          format={figure}
          tick={formatDay}
          unknown={unknown}
          whole
          diverging
        />
      ) : (
        <EmptyState title="No feedback in this window">
          People's thumbs on the agent's messages, artifacts, turns and runs are counted here, each
          day.
        </EmptyState>
      )}
      {drawn.length > 0 ? (
        <LineChart
          label="Each evaluation's mean per day"
          index={DAY}
          series={drawn.map((evaluation) => ({ key: named(evaluation), name: named(evaluation) }))}
          data={summary.days.map((day, at) =>
            Object.fromEntries([
              ["day", day.day],
              ...drawn.map((evaluation) => [
                named(evaluation),
                known(at, evaluation.days[at]?.mean ?? null),
              ]),
            ]),
          )}
          format={mean}
          tick={formatDay}
          unknown={unknown}
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
            {
              key: "count",
              label: "Scores",
              numeric: true,
              cell: (evaluation) => figure(evaluation.count),
            },
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
            key: place.workspace ?? NOWHERE.key,
            name: place.workspace ?? NOWHERE.name,
            value: place.up + place.down,
          }))}
          format={figure}
        />
      )}
      {everywhere && summary.workspaces.length > 0 && (
        <ItemTable
          caption="By workspace"
          columns={[
            {
              key: "workspace",
              label: "Workspace",
              cell: (place) => place.workspace ?? NOWHERE.name,
            },
            { key: "up", label: "Thumbs up", numeric: true, cell: (place) => figure(place.up) },
            {
              key: "down",
              label: "Thumbs down",
              numeric: true,
              cell: (place) => figure(place.down),
            },
            { key: "evaluated", label: "Evaluations", cell: (place) => figure(place.evaluated) },
          ]}
          items={summary.workspaces}
          keyOf={(place) => place.workspace ?? NOWHERE.key}
          empty={{ title: "No feedback yet", body: "Thumbs and evaluations appear here." }}
        />
      )}
    </>
  );
}

/**
 * What people wrote, newest first, each with its trace, which opens here, and, for operators,
 * Langfuse's page beside it.
 */
function Comments({ comments }: { comments: readonly Comment[] }) {
  const { tenant } = Route.useParams();
  const { queries, user } = Route.useRouteContext();
  // An operator reads every tenant; the switch reads this too, so it is cached.
  const { data: every } = useQuery(queries.portalr.tenants(user));
  const operator = every !== null && every !== undefined;
  // Langfuse's page for a trace, read once, for operators alone.
  const { data: links } = useQuery({
    ...queries.portalr.links(user, TEMPLATE),
    enabled: operator,
  });
  const template = links?.langfuse_trace ?? null;
  return (
    <ItemTable
      caption="What people said"
      columns={[
        { key: "comment", label: "Comment", cell: (comment) => comment.text },
        { key: "workspace", label: "Workspace", cell: (comment) => comment.workspace ?? "–" },
        { key: "at", label: "When", cell: (comment) => <Moment at={comment.timestamp} /> },
        {
          key: "trace",
          label: "Trace",
          cell: (comment) => (
            <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <TextLink
                variant="subtle"
                render={
                  <Link
                    to="/t/$tenant/traces/$trace"
                    params={{ tenant, trace: comment.trace_id }}
                  />
                }
              >
                <code className="font-mono text-xs">{comment.trace_id}</code>
              </TextLink>
              {template && (
                <TextLink
                  variant="external"
                  href={template.replace(TEMPLATE, encodeURIComponent(comment.trace_id))}
                >
                  Langfuse
                </TextLink>
              )}
            </span>
          ),
        },
      ]}
      items={comments}
      keyOf={(comment) => comment.id}
      empty={{ title: "No comments yet", body: "What people write beside a thumb is shown here." }}
    />
  );
}

/** The window, and a workspace, or every one: choosing either puts it in the address. */
function Filter({ tenant, shown }: { tenant: string; shown: Required<Shown> }) {
  const navigate = Route.useNavigate();
  const { queries } = Route.useRouteContext();
  // The tenant's workspaces, as artifactr lists them: a suggestion, the form works without it.
  const { data: workspaces } = useQuery(queries.artifactr.workspaces(tenant));
  const go = (next: Partial<Record<keyof Shown, string>>) =>
    void navigate({ search: shownOf({ ...shown, ...next }) });
  const offered = [
    ...new Set([...(workspaces ?? []), ...(shown.workspace ? [shown.workspace] : [])]),
  ];
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <SegmentedFilter
        label="Window"
        showLabel
        hint="Whole days, in UTC."
        segments={WINDOWS.map((days) => ({ value: String(days), label: `${days} days` }))}
        value={String(shown.days)}
        onValueChange={(days) => go({ days })}
      />
      <SelectField
        label="Workspace"
        value={shown.workspace ?? ""}
        onValueChange={(workspace) => go({ workspace })}
        options={[
          { value: "", label: "Every workspace" },
          ...offered.sort().map((one) => ({ value: one, label: one })),
        ]}
      />
    </div>
  );
}
