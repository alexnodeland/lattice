import { PageHeader } from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute, Link, Outlet } from "@tanstack/react-router";
import { useMemo } from "react";
import { accessIn, PARTS } from "../../../../access";

/**
 * Who may see and do what in a tenant: its members, groups and keys, each a part shown where
 * grantr allows its read, as tables on a wide screen and cards on a phone (portalr ADR-0024).
 */
export const Route = createFileRoute("/_signed/t/$tenant/access")({
  head: ({ params }) => ({ meta: [{ title: `Access · ${params.tenant} · portalr admin` }] }),
  component: Access,
});

function Access() {
  const { tenant } = Route.useParams();
  const { queries } = Route.useRouteContext();
  const checks = useMemo(() => accessIn(queries, tenant), [queries, tenant]);
  const { data: allowed } = useSuspenseQuery(checks);
  return (
    <>
      <PageHeader title="Access" meta="Who may see and do what in the tenant" />
      <nav aria-label="Access" className="mb-4 flex flex-wrap gap-1 border-line border-b">
        {PARTS.filter(({ reads }) => allowed.has(reads)).map(({ part, label }) => (
          <Link
            key={part}
            to={`/t/$tenant/access/${part}`}
            params={{ tenant }}
            className="-mb-px border-transparent border-b-2 px-3 py-2 font-medium text-muted text-sm outline-offset-2 hover:text-fg focus-visible:outline-2 focus-visible:outline-focus aria-[current=page]:border-accent aria-[current=page]:text-fg"
          >
            {label}
          </Link>
        ))}
      </nav>
      <Outlet />
    </>
  );
}
