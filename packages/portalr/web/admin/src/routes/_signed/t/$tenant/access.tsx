import { EmptyState, PageHeader, TabLink, TabNav } from "@portalr/ui";
import { createFileRoute, type ErrorComponentProps, Link, Outlet } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { PARTS, useAccess } from "../../../../access";
import { ReadFailed } from "../../../../read-failed";

/**
 * Who may see and do what in a tenant: its members, groups and keys, each a part shown where
 * grantr allows its read, as tables on a wide screen and cards on a phone (portalr ADR-0024). A
 * part that isn't allowed, or whose read failed, says so here, in the tenant's frame.
 */
export const Route = createFileRoute("/_signed/t/$tenant/access")({
  head: ({ params, match }) => ({
    meta: [{ title: match.context.title(`Access · ${params.tenant}`) }],
  }),
  component: () => (
    <Parts>
      <Outlet />
    </Parts>
  ),
  notFoundComponent: () => (
    <Parts>
      <EmptyState focus title="There's no such part of Access here">
        Each part shows where grantr allows you to read it. Choose another above.
      </EmptyState>
    </Parts>
  ),
  errorComponent: Failed,
});

/** Access's heading and the tabs of the parts grantr allows, over what the part shows. */
function Parts({ children }: { children: ReactNode }) {
  const { tenant } = Route.useParams();
  const { allowed } = useAccess(tenant);
  return (
    <>
      <PageHeader title="Access" meta="Who may see and do what in the tenant" />
      {/* The tabs with the part's toolbar close under them, one group (portalr ADR-0085). */}
      <div className="flex flex-col gap-4">
        <TabNav label="Access">
          {PARTS.filter(({ reads }) => allowed.has(reads)).map(({ part, label }) => (
            <TabLink
              key={part}
              render={<Link to={`/t/$tenant/access/${part}`} params={{ tenant }} />}
            >
              {label}
            </TabLink>
          ))}
        </TabNav>
        {children}
      </div>
    </>
  );
}

/** A part whose read failed: what failed, and a way to read it again. */
function Failed({ error, reset }: ErrorComponentProps) {
  return (
    <ReadFailed
      title="This part of Access couldn't be read"
      header={<PageHeader title="Access" meta="Who may see and do what in the tenant" />}
      error={error}
      reset={reset}
    />
  );
}
