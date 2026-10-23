import type { PortalrApi } from "@portalr/client";
import {
  Alert,
  BarChart,
  EmptyState,
  formatDay,
  Heading,
  ItemTable,
  Num,
  PageHeader,
  SegmentedFilter,
  StatusBadge,
} from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import {
  createFileRoute,
  type ErrorComponentProps,
  type SearchSchemaInput,
} from "@tanstack/react-router";
import { opening } from "../../../../access";
import { type Shown, shareOf, shownOf, stepsOf, weekSaid, weeksOf } from "../../../../adoption";
import { numbers } from "../../../../format";
import { ReadFailed } from "../../../../read-failed";
import { WINDOWS, windowOf } from "../../../../window";

type Adoption = PortalrApi.components["schemas"]["Adoption"];

const HEADER = (
  <PageHeader
    title="Adoption"
    meta="How the tenant's people use the product, from those who chose to share it"
  />
);

/** What the axes and tables call a day: one in UTC, as ClickHouse sums them. */
const DAY = { key: "day", name: "Day (UTC)" } as const;

/**
 * A tenant's adoption from its product analytics, for whoever may read its telemetry: people
 * active each day, each integration's people, the funnel from a page to a thread to a message,
 * and weekly retention. Only people who chose to share how they use the app are counted, by a
 * keyed hash of their id. The window is in the address (portalr ADR-0071).
 */
export const Route = createFileRoute("/_signed/t/$tenant/adoption")({
  head: ({ params, match }) => ({
    meta: [{ title: match.context.title(`Adoption · ${params.tenant}`) }],
  }),
  validateSearch: (search: Shown & SearchSchemaInput): Required<Shown> => shownOf(search),
  beforeLoad: ({ context, params }) => opening(context, params.tenant, "portalr:read_telemetry"),
  loaderDeps: ({ search }: { search: Required<Shown> }) => ({
    window: windowOf(search.days, new Date()),
  }),
  loader: async ({ context, params, deps }) => {
    const { queries, queryClient } = context;
    await queryClient.ensureQueryData(queries.portalr.adoption(params.tenant, deps.window));
  },
  component: AdoptionPage,
  notFoundComponent: () => (
    <>
      {HEADER}
      <EmptyState focus title="Adoption isn't yours to read here">
        portalr shows a tenant's adoption to those who may read its telemetry, such as its owners
        and admins.
      </EmptyState>
    </>
  ),
  errorComponent: ({ error, reset }: ErrorComponentProps) => (
    <ReadFailed title="Adoption couldn't be read" header={HEADER} error={error} reset={reset} />
  ),
});

function AdoptionPage() {
  const { tenant } = Route.useParams();
  const shown = Route.useSearch();
  const { window } = Route.useLoaderDeps();
  const { queries } = Route.useRouteContext();
  const { data: reading } = useSuspenseQuery(queries.portalr.adoption(tenant, window));
  if (reading.status === "unconfigured") {
    return (
      <>
        {HEADER}
        <EmptyState title="Product analytics aren't configured">
          Adoption is read from product analytics, which this deployment runs without.
        </EmptyState>
      </>
    );
  }
  if (reading.status === "unavailable") {
    // The reason is the server's, for operators: a tenant reads the kit's own words.
    return (
      <>
        {HEADER}
        <EmptyState title="Product analytics aren't answering">
          <Alert tone="error">Adoption can't be read just now. Try again in a moment.</Alert>
        </EmptyState>
      </>
    );
  }
  const adoption = reading.data;
  return (
    <div className="flex flex-col gap-6">
      {HEADER}
      <Filter shown={shown} />
      {!adoption.complete && (
        <Alert tone="warn">
          <StatusBadge tone="stopped" className="mr-2">
            Partial
          </StatusBadge>
          The read stopped short, so what it didn't reach is left out, not shown as none. A shorter
          window may read it all.
        </Alert>
      )}
      <Active adoption={adoption} />
      <Integrations adoption={adoption} />
      <Funnel adoption={adoption} />
      <Retention adoption={adoption} />
      <p className="text-muted text-sm">
        Only people who chose to share how they use the app are counted, and never what they wrote.
      </p>
    </div>
  );
}

/** How many people were active over the window, and each day. */
function Active({ adoption }: { adoption: Adoption }) {
  return (
    <>
      <p className="text-muted text-sm">
        <span className="font-semibold text-fg text-xl">
          <Num>{numbers.format(adoption.people)}</Num>
        </span>{" "}
        {adoption.people === 1 ? "person was" : "people were"} active over the window.
      </p>
      <BarChart
        label="People active per day"
        index={DAY}
        series={[{ key: "people", name: "People" }]}
        data={adoption.days.map((day) => ({ day: day.day, people: day.people }))}
        format={(people) => numbers.format(people)}
        tick={formatDay}
      />
    </>
  );
}

/** Each integration's people and uses. */
function Integrations({ adoption }: { adoption: Adoption }) {
  return (
    <section aria-labelledby="by-integration" className="flex flex-col gap-3">
      <Heading id="by-integration" level={2} look="subsection">
        By integration
      </Heading>
      <ItemTable
        caption="Each integration's people and uses"
        columns={[
          { key: "integration", label: "Integration", cell: (use) => use.integration },
          { key: "people", label: "People", cell: (use) => numbers.format(use.people) },
          {
            key: "share",
            label: "Of everyone active",
            cell: (use) => shareOf(use.people, adoption.people),
          },
          { key: "uses", label: "Uses", cell: (use) => numbers.format(use.uses) },
        ]}
        items={adoption.integrations}
        keyOf={(use) => use.integration}
        empty={{
          title: "No integration was used in this window",
          body: "An integration is counted when someone uses it in the app.",
        }}
      />
    </section>
  );
}

/** How far people went, from a page to a thread to a message, within a day. */
function Funnel({ adoption }: { adoption: Adoption }) {
  const steps = adoption.funnel ? stepsOf(adoption.funnel) : [];
  const first = steps[0]?.people ?? 0;
  return (
    <section aria-labelledby="funnel" className="flex flex-col gap-3">
      <Heading id="funnel" level={2} look="subsection">
        From a page to a message
      </Heading>
      <ItemTable
        caption="People at each step, within a day of the first"
        columns={[
          { key: "step", label: "Step", cell: (step) => step.name },
          { key: "people", label: "People", cell: (step) => numbers.format(step.people) },
          { key: "share", label: "Of the first step", cell: (step) => shareOf(step.people, first) },
        ]}
        items={steps}
        keyOf={(step) => step.key}
        empty={{
          title: "The funnel wasn't read",
          body: "The read stopped before it reached the funnel.",
        }}
      />
    </section>
  );
}

/** Of the window's first week's people, how many were active in each week of it. */
function Retention({ adoption }: { adoption: Adoption }) {
  const weeks = weeksOf(adoption.retention);
  const first = weeks[0]?.people ?? 0;
  return (
    <section aria-labelledby="retention" className="flex flex-col gap-3">
      <Heading id="retention" level={2} look="subsection">
        Weekly retention
      </Heading>
      <ItemTable
        caption="Of the people active in the window's first week, those active in each week"
        columns={[
          { key: "week", label: "Week", cell: (week) => weekSaid(week.week) },
          { key: "people", label: "People", cell: (week) => numbers.format(week.people) },
          { key: "share", label: "Of week 1", cell: (week) => shareOf(week.people, first) },
        ]}
        items={weeks}
        keyOf={(week) => String(week.week)}
        empty={{
          title: "No one was active in the window's first week",
          body: "Retention follows the people active in the first week of the window.",
        }}
      />
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
      hint="Whole days, in UTC."
      segments={WINDOWS.map((days) => ({ value: String(days), label: `${days} days` }))}
      value={String(shown.days)}
      onValueChange={(days) => void navigate({ search: shownOf({ days }) })}
    />
  );
}
