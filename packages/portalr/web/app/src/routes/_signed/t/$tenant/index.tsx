import { Account, AppShell, PageHeader, Row, RowLink, Rows, Switcher, TextLink } from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";

/**
 * The workspaces the caller can open in the tenant, as grantr lists them, in order, in the app's
 * frame: each a card with its name, which opens it, and a link to each of its areas. Nothing is
 * read per workspace; the frame's switcher names the tenant alone.
 */
export const Route = createFileRoute("/_signed/t/$tenant/")({
  head: ({ params }) => ({ meta: [{ title: `Workspaces · ${params.tenant} · portalr` }] }),
  loader: ({ context }) =>
    context.queryClient.ensureQueryData(context.queries.grantr.memberships(context.user)),
  component: Workspaces,
});

/** A workspace's areas, each a link from its card. */
const AREAS = [
  { to: "/t/$tenant/w/$workspace", label: "Threads" },
  { to: "/t/$tenant/w/$workspace/artifacts", label: "Artifacts" },
  { to: "/t/$tenant/w/$workspace/proposals", label: "Proposals" },
  { to: "/t/$tenant/w/$workspace/runs", label: "Runs" },
  { to: "/t/$tenant/w/$workspace/rules", label: "Rules" },
] as const;

function Workspaces() {
  const { tenant } = Route.useParams();
  const { queries, signed, user } = Route.useRouteContext();
  const navigate = useNavigate();
  const { data: memberships } = useSuspenseQuery(queries.grantr.memberships(user));
  const { data: me } = useSuspenseQuery(queries.grantr.me(tenant));
  const tenants = [...new Set(memberships.map((membership) => membership.tenant))].sort();
  const workspaces = [...me.workspaces].sort();
  return (
    <AppShell
      home={<Link to="/" />}
      switcher={
        <Switcher
          tenant={tenant}
          tenants={tenants.map((id) => ({ id }))}
          workspaces={workspaces.map((id) => ({ id }))}
          onTenant={(id) => void navigate({ to: "/t/$tenant", params: { tenant: id } })}
          onWorkspace={(id) =>
            void navigate({ to: "/t/$tenant/w/$workspace", params: { tenant, workspace: id } })
          }
        />
      }
      account={<Account signed={signed} />}
    >
      <PageHeader title={tenant} meta="The workspaces you can open here" />
      {workspaces.length === 0 ? (
        <p>There is no workspace here you can open.</p>
      ) : (
        <Rows label="Workspaces">
          {workspaces.map((workspace) => (
            <Row key={workspace}>
              <RowLink
                render={<Link to="/t/$tenant/w/$workspace" params={{ tenant, workspace }} />}
              >
                {workspace}
              </RowLink>
              <ul
                aria-label={`${workspace}'s areas`}
                className="relative z-10 ml-auto flex flex-wrap gap-x-4 gap-y-1"
              >
                {AREAS.map(({ to, label }) => (
                  <li key={label}>
                    <TextLink
                      variant="nav"
                      className="text-sm"
                      render={<Link to={to} params={{ tenant, workspace }} />}
                    >
                      {label}
                    </TextLink>
                  </li>
                ))}
              </ul>
            </Row>
          ))}
        </Rows>
      )}
    </AppShell>
  );
}
