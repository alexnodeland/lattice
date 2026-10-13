import { AppShell, NavLink, SideNav, Switcher } from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute, Link, Outlet, useMatchRoute, useNavigate } from "@tanstack/react-router";
import { FileText, MessageSquare, Play, Workflow, Zap } from "lucide-react";
import { Account } from "../../../../../account";
import { useWorkspace, WorkspaceStreams } from "../../../../../workspace";

/**
 * A workspace: its streams, open while any of its areas is, and its frame, ui's AppShell, with
 * the way between its areas, between workspaces and tenants, and the account.
 */
export const Route = createFileRoute("/_signed/t/$tenant/w/$workspace")({
  head: ({ params }) => ({ meta: [{ title: `${params.workspace} · ${params.tenant} · portalr` }] }),
  loader: ({ context }) =>
    context.queryClient.ensureQueryData(context.queries.grantr.memberships(context.user)),
  component: Workspace,
});

function Workspace() {
  const { tenant, workspace } = Route.useParams();
  const { config, signed, queries, user } = Route.useRouteContext();
  const navigate = useNavigate();
  const { data: memberships } = useSuspenseQuery(queries.grantr.memberships(user));
  const { data: me } = useSuspenseQuery(queries.grantr.me(tenant));
  const tenants = [...new Set(memberships.map((membership) => membership.tenant))].sort();
  return (
    <WorkspaceStreams
      key={`${tenant}/${workspace}`}
      surfaces={config.surfaces}
      signed={signed}
      tenant={tenant}
      workspace={workspace}
    >
      <AppShell
        home={<Link to="/" />}
        switcher={
          <Switcher
            tenant={tenant}
            workspace={workspace}
            tenants={tenants.map((id) => ({ id }))}
            workspaces={[...me.workspaces].sort().map((id) => ({ id }))}
            onTenant={(id) => void navigate({ to: "/t/$tenant", params: { tenant: id } })}
            onWorkspace={(id) =>
              void navigate({
                to: "/t/$tenant/w/$workspace",
                params: { tenant, workspace: id },
              })
            }
            every={<Link to="/t/$tenant" params={{ tenant }} />}
          />
        }
        nav={<Areas tenant={tenant} workspace={workspace} />}
        account={<Account signed={signed} />}
      >
        <Outlet />
      </AppShell>
    </WorkspaceStreams>
  );
}

/**
 * The workspace's areas, the current one marked, with what waits for the reader: turns paused
 * for an answer, and open proposals. Threads is current on a thread's page as well as its own.
 */
function Areas({ tenant, workspace }: { tenant: string; workspace: string }) {
  const params = { tenant, workspace };
  const { state } = useWorkspace();
  const onThread = useMatchRoute()({
    to: "/t/$tenant/w/$workspace/threads/$thread",
    params,
    fuzzy: true,
  });
  const paused = Object.values(state.runs).filter((run) => run.status === "paused").length;
  const open = Object.values(state.proposals).filter((proposal) => proposal.status === "open");
  return (
    <SideNav label="Workspace">
      <NavLink
        icon={MessageSquare}
        count={paused}
        render={
          <Link
            to="/t/$tenant/w/$workspace"
            params={params}
            activeOptions={{ exact: true }}
            {...(onThread && { "aria-current": "true" })}
          />
        }
      >
        Threads
      </NavLink>
      <NavLink
        icon={FileText}
        render={<Link to="/t/$tenant/w/$workspace/artifacts" params={params} />}
      >
        Artifacts
      </NavLink>
      <NavLink
        icon={Workflow}
        count={open.length}
        render={<Link to="/t/$tenant/w/$workspace/proposals" params={params} />}
      >
        Proposals
      </NavLink>
      <NavLink icon={Play} render={<Link to="/t/$tenant/w/$workspace/runs" params={params} />}>
        Runs
      </NavLink>
      <NavLink icon={Zap} render={<Link to="/t/$tenant/w/$workspace/rules" params={params} />}>
        Rules
      </NavLink>
    </SideNav>
  );
}
