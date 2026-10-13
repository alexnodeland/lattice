import { PageHeader, StatCard } from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { counted, dollars, type Reading, unread } from "../../../home";

/** Every tenant at a glance, for operators: how many there are, and what they spend. */
export const Route = createFileRoute("/_signed/deployment/")({ component: Home });

function Home() {
  const { queries } = Route.useRouteContext();
  const { data: every } = useSuspenseQuery(queries.portalr.tenants());
  const tenants = every?.tenants ?? [];
  const spend = every?.spend;
  const said = spend === undefined ? null : unread("LiteLLM", spend as Reading<unknown>);
  const total =
    spend?.status === "ok" ? spend.data.reduce((sum, each) => sum + each.spend, 0) : null;
  return (
    <>
      <PageHeader title="All tenants" meta="The deployment, for its operators" />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <StatCard title="Tenants" figure={String(tenants.length)}>
          {counted(tenants.length, "tenant")} in grantr
        </StatCard>
        <StatCard title="Spend" figure={said?.figure ?? (total === null ? null : dollars(total))}>
          {said?.line ?? "across every tenant's LiteLLM team"}
        </StatCard>
      </div>
    </>
  );
}
