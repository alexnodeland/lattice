import type { PortalrApi } from "@portalr/client";
import {
  BarChart,
  Button,
  EmptyState,
  ItemTable,
  LineChart,
  PageHeader,
  SelectField,
} from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute, type ErrorComponentProps, useRouter } from "@tanstack/react-router";
import { useMemo } from "react";
import { opening } from "../../../../access";
import {
  byWorkspace,
  comments,
  daysIn,
  SERIES,
  type Shown,
  shownOf,
  thumbsByDay,
  trends,
  WINDOWS,
  windowOf,
} from "../../../../feedback";
import { figure, LIMIT } from "../../../../home";

type Score = PortalrApi.components["schemas"]["Score"];

const HEADER = <PageHeader title="Feedback" meta="What people and evaluators said of the agent" />;

/** A mean as people read it: two places. */
const mean = (value: number) => value.toFixed(2);

/**
 * A tenant's feedback and evaluations from Langfuse, for whoever may read its telemetry: people's
 * thumbs per day, each evaluation's mean per day, each workspace's share, and what people said.
 * The window and a workspace are in the address, so a view can be linked to (portalr ADR-0027).
 */
export const Route = createFileRoute("/_signed/t/$tenant/feedback")({
  head: ({ params }) => ({ meta: [{ title: `Feedback · ${params.tenant} · portalr admin` }] }),
  validateSearch: (search: Record<string, unknown>): Shown => shownOf(search),
  beforeLoad: ({ context, params }) =>
    opening(context, params.tenant, "portalr:read_telemetry"),
  loaderDeps: ({ search }) => ({ days: search.days }),
  loader: ({ context, params, deps }) =>
    context.queryClient.ensureQueryData(
      context.queries.portalr.scores(params.tenant, windowOf(deps.days, new Date())),
    ),
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
  errorComponent: Failed,
});

function Feedback() {
  const { tenant } = Route.useParams();
  const shown = Route.useSearch();
  const { queries } = Route.useRouteContext();
  const window = useMemo(() => windowOf(shown.days, new Date()), [shown.days]);
  const { data: reading } = useSuspenseQuery(queries.portalr.scores(tenant, window));
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
  return (
    <div className="flex flex-col gap-6">
      {HEADER}
      <Filter shown={shown} places={byWorkspace(reading.data).map((place) => place.workspace)} />
      {reading.data.length >= LIMIT && (
        <p role="status" className="text-muted text-sm">
          {figure(reading.data.length, LIMIT)} scores: the newest {figure(LIMIT)} are shown. Choose
          a shorter window, or a workspace, to see them all.
        </p>
      )}
      <Read
        scores={reading.data.filter(
          (score) => shown.workspace === undefined || score.workspace === shown.workspace,
        )}
        days={daysIn(window)}
        everywhere={shown.workspace === undefined}
      />
    </div>
  );
}

/** What the scores say: the charts, each workspace's share, and what people wrote. */
function Read({
  scores,
  days,
  everywhere,
}: {
  scores: readonly Score[];
  days: readonly string[];
  everywhere: boolean;
}) {
  const evaluations = trends(scores, days);
  const said = comments(scores).slice(0, 20);
  return (
    <>
      <BarChart
        label="People's thumbs per day"
        index={{ key: "day", name: "Day" }}
        series={[
          { key: "up", name: "Thumbs up" },
          { key: "down", name: "Thumbs down" },
        ]}
        data={thumbsByDay(scores, days)}
        diverging
      />
      {evaluations.length > 0 ? (
        <LineChart
          label="Each evaluation's mean per day"
          index={{ key: "day", name: "Day" }}
          series={evaluations.slice(0, SERIES).map((trend) => ({
            key: trend.name,
            name: trend.name,
          }))}
          data={days.map((day) =>
            Object.fromEntries([
              ["day", day],
              ...evaluations
                .slice(0, SERIES)
                .map((trend) => [
                  trend.name,
                  trend.points.find((point) => point.day === day)?.mean ?? null,
                ]),
            ]),
          )}
          format={mean}
        />
      ) : (
        <EmptyState title="No evaluations in this window">
          An evaluator's numeric or yes-or-no scores are averaged here, each day.
        </EmptyState>
      )}
      {evaluations.length > SERIES && (
        <ItemTable
          caption="Every evaluation"
          columns={[
            { key: "name", label: "Evaluation", cell: (trend) => trend.name },
            { key: "count", label: "Scores", cell: (trend) => figure(trend.count) },
          ]}
          items={evaluations}
          keyOf={(trend) => trend.name}
          empty={{ title: "No evaluations", body: "None in this window." }}
        />
      )}
      {everywhere && (
        <ItemTable
          caption="By workspace"
          columns={[
            {
              key: "workspace",
              label: "Workspace",
              cell: (place) => place.workspace ?? "In no workspace",
            },
            { key: "up", label: "Thumbs up", cell: (place) => figure(place.up) },
            { key: "down", label: "Thumbs down", cell: (place) => figure(place.down) },
            { key: "evaluated", label: "Evaluations", cell: (place) => figure(place.evaluated) },
          ]}
          items={byWorkspace(scores)}
          keyOf={(place) => place.workspace ?? "~none"}
          empty={{ title: "No feedback yet", body: "Thumbs and evaluations appear here." }}
        />
      )}
      <ItemTable
        caption="What people said"
        columns={[
          { key: "comment", label: "Comment", cell: (score) => score.comment },
          {
            key: "thumb",
            label: "Thumb",
            cell: (score) =>
              score.value === true ? "Up" : score.value === false ? "Down" : String(score.value),
          },
          { key: "workspace", label: "Workspace", cell: (score) => score.workspace ?? "–" },
          {
            key: "at",
            label: "When",
            cell: (score) => (
              <time dateTime={score.timestamp}>{new Date(score.timestamp).toLocaleString()}</time>
            ),
          },
          {
            key: "trace",
            label: "Trace",
            cell: (score) => <code className="font-mono text-xs">{score.trace_id}</code>,
          },
        ]}
        items={said}
        keyOf={(score) => score.id}
        empty={{ title: "No comments yet", body: "What people write beside a thumb is shown here." }}
      />
    </>
  );
}

/** The window, and a workspace, or every one: choosing either puts it in the address. */
function Filter({ shown, places }: { shown: Shown; places: readonly (string | null)[] }) {
  const navigate = Route.useNavigate();
  const named = places.filter((place) => place !== null);
  const go = (next: Partial<Record<keyof Shown, string>>) =>
    void navigate({ search: shownOf({ ...shown, ...next }) });
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <SelectField
        label="Window"
        value={String(shown.days)}
        onChange={(event) => go({ days: event.target.value })}
        options={WINDOWS.map((days) => ({ value: String(days), label: `The last ${days} days` }))}
      />
      <SelectField
        label="Workspace"
        value={shown.workspace ?? ""}
        onChange={(event) => go({ workspace: event.target.value })}
        options={[
          { value: "", label: "Every workspace" },
          ...[...new Set([...named, ...(shown.workspace ? [shown.workspace] : [])])]
            .sort()
            .map((workspace) => ({ value: workspace, label: workspace })),
        ]}
      />
    </div>
  );
}

/** The read failed: what failed, and a way to read it again. */
function Failed({ error, reset }: ErrorComponentProps) {
  const router = useRouter();
  return (
    <>
      {HEADER}
      <EmptyState
        title="Feedback couldn't be read"
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
