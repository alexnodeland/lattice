import { PageHeader, StatCard, StatusBadge } from "@portalr/ui";
import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import {
  budget,
  counted,
  dollars,
  failures,
  type Reading,
  type Said,
  unread,
  windowOf,
} from "../../../../home";

/**
 * A tenant's Home: its members and workspaces, feedback, failed runs and spend, each a card from
 * one read, with its own state, so a tool that is down fails its own card alone.
 */
export const Route = createFileRoute("/_signed/t/$tenant/")({ component: Home });

/** Five minutes: the step between the failed-runs series' points, as wide as its rate's window. */
const STEP = 300;

function Home() {
  const { tenant } = Route.useParams();
  return (
    <>
      <PageHeader title={tenant} meta="How the tenant is doing" />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <Members tenant={tenant} />
        <Workspaces tenant={tenant} />
        <Feedback tenant={tenant} />
        <Failures tenant={tenant} />
        <Spend tenant={tenant} />
      </div>
    </>
  );
}

/** A card while its read is out, or when it was refused: its own state, and no figure. */
function pending(isPending: boolean, error: unknown): Said | null {
  if (isPending) {
    return { figure: null, line: "Reading…" };
  }
  return error ? { figure: null, line: "This couldn't be read." } : null;
}

function Members({ tenant }: { tenant: string }) {
  const { queries } = Route.useRouteContext();
  const { data, isPending, error } = useQuery(queries.grantr.members(tenant));
  const people = data?.filter((member) => member.kind === "user").length ?? 0;
  const principals = (data?.length ?? 0) - people;
  const said = pending(isPending, error) ?? {
    figure: String(data?.length ?? 0),
    line: `${counted(people, "person", "people")} and ${counted(principals, "service principal")}`,
  };
  return (
    <StatCard title="Members" figure={said.figure}>
      {said.line}
    </StatCard>
  );
}

function Workspaces({ tenant }: { tenant: string }) {
  const { queries } = Route.useRouteContext();
  const { data, isPending, error } = useQuery(queries.artifactr.workspaces(tenant));
  const said = pending(isPending, error) ?? {
    figure: String(data?.length ?? 0),
    line: "with a log in artifactr",
  };
  return (
    <StatCard title="Workspaces" figure={said.figure}>
      {said.line}
    </StatCard>
  );
}

function Feedback({ tenant }: { tenant: string }) {
  const { queries } = Route.useRouteContext();
  const [week] = useState(() => windowOf(new Date(), 7));
  const { data, isPending, error } = useQuery(queries.portalr.scores(tenant, week));
  const said =
    pending(isPending, error) ??
    unread("Langfuse", data as Reading<unknown>) ??
    (() => {
      const scores = data?.status === "ok" ? data.data : [];
      const thumbs = scores.filter((score) => typeof score.value === "boolean");
      const up = thumbs.filter((score) => score.value === true).length;
      return {
        figure: String(scores.length),
        line: thumbs.length
          ? `scores in the last week; ${up} of ${thumbs.length} thumbs up`
          : "scores in the last week",
      };
    })();
  return (
    <StatCard title="Feedback" figure={said.figure}>
      {said.line}
    </StatCard>
  );
}

function Failures({ tenant }: { tenant: string }) {
  const { queries } = Route.useRouteContext();
  const [day] = useState(() => windowOf(new Date(), 1, STEP));
  const { data, isPending, error } = useQuery(queries.portalr.metrics(tenant, "failed_runs", day));
  const said = pending(isPending, error) ??
    unread("Prometheus", data as Reading<unknown>) ?? {
      figure: String(failures(data?.status === "ok" ? data.data : [], STEP)),
      line: "failed turns, about, in the last day",
    };
  return (
    <StatCard title="Failed turns" figure={said.figure}>
      {said.line}
    </StatCard>
  );
}

function Spend({ tenant }: { tenant: string }) {
  const { queries } = Route.useRouteContext();
  const { data, isPending, error } = useQuery(queries.portalr.spend(tenant));
  const said = pending(isPending, error) ?? unread("LiteLLM", data as Reading<unknown>);
  if (said) {
    return (
      <StatCard title="Spend" figure={said.figure}>
        {said.line}
      </StatCard>
    );
  }
  const spend = data?.status === "ok" ? data.data : null;
  if (spend === null || spend === undefined) {
    return (
      <StatCard title="Spend" figure={null}>
        The tenant has no team in LiteLLM yet.
      </StatCard>
    );
  }
  const state = budget(spend);
  return (
    <StatCard title="Spend" figure={dollars(spend.spend)}>
      {state === "none" ? (
        "No budget is set."
      ) : (
        <span className="flex flex-wrap items-center gap-2">
          of {dollars(spend.max_budget ?? 0)}
          {spend.budget_duration && ` a ${spend.budget_duration}`}
          {state === "near" && <StatusBadge tone="near">Near budget</StatusBadge>}
          {state === "over" && <StatusBadge tone="over">Over budget</StatusBadge>}
        </span>
      )}
    </StatCard>
  );
}
