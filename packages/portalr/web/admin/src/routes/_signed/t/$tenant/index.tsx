import { PageHeader } from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { Guarded, SaidCard } from "../../../../card";
import {
  failuresSaid,
  feedbackSaid,
  membersSaid,
  spanOf,
  spendSaid,
  workspacesSaid,
} from "../../../../home";

/**
 * A tenant's Home: its members and workspaces, people's feedback, failed turns and spend, each a
 * card from one read, with its own state, so a tool that is down fails its own card alone.
 */
export const Route = createFileRoute("/_signed/t/$tenant/")({ component: Home });

/** A day: Failed turns reads one point, which counts the failures in the day before it. */
const DAY = 86_400;

function Home() {
  const { tenant } = Route.useParams();
  return (
    <>
      <PageHeader title={tenant} meta="How the tenant is doing" />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <Guarded title="Members">
          <Members tenant={tenant} />
        </Guarded>
        <Guarded title="Workspaces">
          <Workspaces tenant={tenant} />
        </Guarded>
        <Guarded title="Feedback">
          <Feedback tenant={tenant} />
        </Guarded>
        <Guarded title="Failed turns">
          <Failures tenant={tenant} />
        </Guarded>
        <Guarded title="Spend">
          <Spend tenant={tenant} />
        </Guarded>
      </div>
    </>
  );
}

function Members({ tenant }: { tenant: string }) {
  const { queries } = Route.useRouteContext();
  const { data } = useSuspenseQuery(queries.grantr.members(tenant));
  return <SaidCard title="Members" said={membersSaid(data)} />;
}

function Workspaces({ tenant }: { tenant: string }) {
  const { queries } = Route.useRouteContext();
  const { data } = useSuspenseQuery(queries.artifactr.workspaces(tenant));
  return <SaidCard title="Workspaces" said={workspacesSaid(data)} />;
}

function Feedback({ tenant }: { tenant: string }) {
  const { queries } = Route.useRouteContext();
  const [week] = useState(() => spanOf(new Date(), 7));
  const { data } = useSuspenseQuery(queries.portalr.scores(tenant, week));
  return <SaidCard title="Feedback" said={feedbackSaid(data)} />;
}

function Failures({ tenant }: { tenant: string }) {
  const { queries } = Route.useRouteContext();
  const [day] = useState(() => spanOf(new Date(), 1, DAY));
  const { data } = useSuspenseQuery(queries.portalr.metrics(tenant, "failed_turns", day));
  return <SaidCard title="Failed turns" said={failuresSaid(data)} />;
}

function Spend({ tenant }: { tenant: string }) {
  const { queries } = Route.useRouteContext();
  const { data } = useSuspenseQuery(queries.portalr.spend(tenant));
  return <SaidCard title="Spend" said={spendSaid(data)} />;
}
