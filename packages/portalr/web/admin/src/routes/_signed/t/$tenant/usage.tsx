import type { PortalrApi } from "@portalr/client";
import {
  BarChart,
  DonutChart,
  EmptyState,
  ItemTable,
  PageHeader,
  SegmentedFilter,
  StatusBadge,
  Tracker,
} from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import {
  createFileRoute,
  type ErrorComponentProps,
  type SearchSchemaInput,
} from "@tanstack/react-router";
import { opening } from "../../../../access";
import { dollars, numbers } from "../../../../format";
import { ReadFailed } from "../../../../read-failed";
import {
  askedOf,
  blocksOf,
  LEVELS,
  MOST_WORKSPACES,
  partsOf,
  type Shown,
  short,
  shownOf,
  trackerLabel,
} from "../../../../usage";
import { WINDOWS, windowOf } from "../../../../window";

type Usage = PortalrApi.components["schemas"]["Usage"];

const HEADER = <PageHeader title="Usage" meta="What the tenant's agents spent, from LiteLLM" />;

/** What the axes and tables call a day: one in UTC, as LiteLLM sums them. */
const DAY = { key: "day", name: "Day (UTC)" } as const;

/**
 * A tenant's usage and spend from LiteLLM, for whoever may read its spend: each day's spend, and
 * against its share of the team's budget, where it has one; and each workspace's part, from the
 * tag the libraries' gateways send. The window is in the address (portalr ADR-0028).
 */
export const Route = createFileRoute("/_signed/t/$tenant/usage")({
  head: ({ params }) => ({ meta: [{ title: `Usage · ${params.tenant} · portalr admin` }] }),
  // What a link may give, optional; what the address gives, read with `shownOf`.
  validateSearch: (search: Shown & SearchSchemaInput): Required<Shown> => shownOf(search),
  beforeLoad: ({ context, params }) => opening(context, params.tenant, "portalr:read_spend"),
  // The window, worked out once, from the day it is: the same all day.
  loaderDeps: ({ search }: { search: Required<Shown> }) => ({
    window: windowOf(search.days, new Date()),
  }),
  // The workspaces to split the spend by are the tenant's, as artifactr lists them; without
  // them, the spend is read whole.
  loader: async ({ context, params, deps }) => {
    const { queries, queryClient } = context;
    const listed = await queryClient
      .ensureQueryData(queries.artifactr.workspaces(params.tenant))
      .catch(() => undefined);
    await queryClient.ensureQueryData(
      queries.portalr.usage(params.tenant, deps.window, askedOf(listed ?? [])),
    );
  },
  component: UsagePage,
  notFoundComponent: () => (
    <>
      {HEADER}
      <EmptyState title="Usage isn't yours to read here">
        portalr shows a tenant's spend to those who may read it, such as its owners and admins.
      </EmptyState>
    </>
  ),
  errorComponent: ({ error, reset }: ErrorComponentProps) => (
    <ReadFailed title="Usage couldn't be read" header={HEADER} error={error} reset={reset} />
  ),
});

function UsagePage() {
  const { tenant } = Route.useParams();
  const shown = Route.useSearch();
  const { window } = Route.useLoaderDeps();
  const { queries, queryClient } = Route.useRouteContext();
  // As the loader read them, and not read again here: the list the usage read was asked with is
  // the list this page shows. None, if artifactr refused it, and the spend is read whole.
  const listed = queryClient.getQueryData(queries.artifactr.workspaces(tenant).queryKey);
  const workspaces = askedOf(listed ?? []);
  const { data: reading } = useSuspenseQuery(queries.portalr.usage(tenant, window, workspaces));
  if (reading.status === "unconfigured") {
    return (
      <>
        {HEADER}
        <EmptyState title="LiteLLM isn't configured">
          Usage and spend are read from LiteLLM, which this deployment runs without.
        </EmptyState>
      </>
    );
  }
  if (reading.status === "unavailable") {
    return (
      <>
        {HEADER}
        <EmptyState title="LiteLLM isn't answering">
          <p role="alert">{reading.reason}</p>
        </EmptyState>
      </>
    );
  }
  const usage = reading.data;
  return (
    <div className="flex flex-col gap-6">
      {HEADER}
      <Filter shown={shown} />
      {!usage.complete && (
        <p role="status" className="flex flex-wrap items-center gap-2 text-muted text-sm">
          <StatusBadge tone="stopped">Partial</StatusBadge>
          The read stopped at one of its bounds. The days it didn't reach, and the last it read,
          which may be part-read, are left out, not shown as nothing spent, and the sums are of what
          it read. A shorter window may read it all.
        </p>
      )}
      <Spent usage={usage} />
      <Workspaces
        usage={usage}
        listed={listed !== undefined}
        more={(listed?.length ?? 0) > MOST_WORKSPACES}
      />
    </div>
  );
}

/** The window's spend, each day's, and, where the team has a budget, each against its share. */
function Spent({ usage }: { usage: Usage }) {
  const spent = usage.days.reduce((sum, day) => sum + day.spend, 0);
  const requests = usage.days.reduce((sum, day) => sum + day.requests, 0);
  const { budget, daily_budget: share } = usage;
  return (
    <>
      <p className="text-muted text-sm">
        <span className="font-semibold text-fg text-xl tabular-nums">{dollars(spent)}</span> in{" "}
        {numbers.format(requests)} requests over the window.
      </p>
      {share != null && budget && (
        <Tracker
          label={trackerLabel(share, budget)}
          index={DAY.name}
          figure="Spend"
          levels={LEVELS}
          blocks={blocksOf(usage, share)}
        />
      )}
      <BarChart
        label="Spend per day"
        index={DAY}
        series={[{ key: "spend", name: "Spend" }]}
        data={usage.days.map((day) => ({ day: day.day, spend: day.spend }))}
        format={dollars}
        tick={short}
      />
    </>
  );
}

/** Each workspace's part of the spend, from its tag, and what no workspace's tag holds. */
function Workspaces({ usage, listed, more }: { usage: Usage; listed: boolean; more: boolean }) {
  const parts = partsOf(usage);
  return (
    <section aria-labelledby="by-workspace" className="flex flex-col gap-3">
      <h2 id="by-workspace" className="font-semibold text-fg">
        By workspace
      </h2>
      {usage.workspaces.length > 0 && (
        <DonutChart label="Spend by workspace" parts={parts} format={dollars} />
      )}
      <ItemTable
        caption="Each workspace's spend"
        columns={[
          { key: "workspace", label: "Workspace", cell: (place) => place.workspace },
          { key: "spend", label: "Spend", cell: (place) => dollars(place.spend) },
          { key: "tokens", label: "Tokens", cell: (place) => numbers.format(place.tokens) },
        ]}
        items={usage.workspaces}
        keyOf={(place) => place.workspace}
        empty={{
          title: "No workspace's spend in this window",
          body: "Spend is split by the workspace each request's tag names.",
        }}
      />
      <p className="text-muted text-sm">
        Spend recorded before the libraries tagged each request with its workspace has no workspace
        split, and is counted under "No workspace".
        {!listed && " artifactr didn't list the tenant's workspaces, so the spend is read whole."}
        {more && ` Only the first ${MOST_WORKSPACES} workspaces, by name, are split out.`}
      </p>
    </section>
  );
}

/** The window: choosing it puts it in the address. */
function Filter({ shown }: { shown: Required<Shown> }) {
  const navigate = Route.useNavigate();
  return (
    <SegmentedFilter
      label="Window"
      showLabel
      hint="The last days, whole and in UTC."
      segments={WINDOWS.map((days) => ({ value: String(days), label: `${days} days` }))}
      value={String(shown.days)}
      onValueChange={(days) => void navigate({ search: shownOf({ days }) })}
    />
  );
}
