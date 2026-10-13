import { PageHeader } from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";
import { SaidCard } from "../../../card";
import { deploymentSpendSaid, figure } from "../../../home";

/** Every tenant at a glance, for operators: how many there are, and what they spend. */
export const Route = createFileRoute("/_signed/deployment/")({ component: Home });

function Home() {
  const { queries, user } = Route.useRouteContext();
  // The deployment's layout read it before letting an operator in.
  const { data: every } = useSuspenseQuery(queries.portalr.tenants(user));
  return (
    <>
      <PageHeader title="All tenants" meta="The deployment, for its operators" />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        <SaidCard
          title="Tenants"
          said={{ figure: figure(every?.tenants.length ?? 0), line: "in grantr" }}
        />
        {every && <SaidCard title="Spend" said={deploymentSpendSaid(every.spend)} />}
      </div>
    </>
  );
}
