import {
  AppShell,
  ButtonLink,
  glyphs,
  IconButton,
  StatusBadge,
  Switcher,
  TrackLink,
  Tracks,
} from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute, Link, Outlet, useMatchRoute, useNavigate } from "@tanstack/react-router";
import { AppAccount } from "../../../../../analytics";
import { SearchButton, SearchPalette } from "../../../../../search";
import { useWorkspace, WorkspaceAddons, WorkspaceStreams } from "../../../../../workspace";

/**
 * A workspace: its streams, open while any of its areas is, its integrations, read as it opens,
 * and its frame, ui's AppShell (portalr ADR-0087): a bar with the way between workspaces and
 * tenants, its areas, its search, what waits for the reader, and the account. Integrations that
 * can't be read are their defaults, never a failed page.
 */
export const Route = createFileRoute("/_signed/t/$tenant/w/$workspace")({
  head: ({ params, match }) => ({
    meta: [
      {
        title: match.context.title(`${params.workspace} · ${params.tenant}`),
      },
    ],
  }),
  loader: ({ context, params }) => {
    // Started, not waited on: the page opens on each integration's default while grantr answers.
    void context.queryClient.prefetchQuery(
      context.queries.grantr.enabledIntegrations(params.tenant, params.workspace),
    );
    return context.queryClient.ensureQueryData(context.queries.grantr.memberships(context.user));
  },
  component: Workspace,
});

function Workspace() {
  const { tenant, workspace } = Route.useParams();
  const { config, signed, queries, user } = Route.useRouteContext();
  const navigate = useNavigate();
  const { data: memberships } = useSuspenseQuery(queries.grantr.memberships(user));
  const { data: me } = useSuspenseQuery(queries.grantr.me(tenant));
  const tenants = [...new Set(memberships.map((membership) => membership.tenant))].sort();
  // A thread is a task of its own: on a phone its foot is its composer, not the tab bar, and its
  // way back to the threads is at the bar's start (portalr ADR-0087).
  const onThread = useMatchRoute()({
    to: "/t/$tenant/w/$workspace/threads/$thread",
    params: { tenant, workspace },
    fuzzy: true,
  });
  return (
    <WorkspaceStreams
      key={`${tenant}/${workspace}`}
      surfaces={config.surfaces}
      signed={signed}
      tenant={tenant}
      workspace={workspace}
    >
      <SearchPalette tenant={tenant} workspace={workspace}>
        <AppShell
          home={<Link to="/" />}
          switcher={
            <>
              {onThread && (
                <IconButton
                  label="All threads"
                  icon={glyphs.chevronLeft}
                  className="hidden phone:flex"
                  render={<Link to="/t/$tenant/w/$workspace" params={{ tenant, workspace }} />}
                />
              )}
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
            </>
          }
          nav={<Areas tenant={tenant} workspace={workspace} />}
          search={<SearchButton {...(!onThread && { className: "phone:hidden" })} />}
          tabs={
            onThread ? null : (
              <>
                <Areas tenant={tenant} workspace={workspace} bar />
                <SearchButton docked />
              </>
            )
          }
          waiting={<NeedYou tenant={tenant} workspace={workspace} />}
          account={<AppAccount />}
        >
          <WorkspaceAddons queries={queries} tenant={tenant} workspace={workspace}>
            <Outlet />
          </WorkspaceAddons>
        </AppShell>
      </SearchPalette>
    </WorkspaceStreams>
  );
}

/**
 * The workspace's areas, the current one marked, with the open proposals beside Proposals. Threads
 * is current on a thread's page as well as its own.
 */
function Areas({
  tenant,
  workspace,
  bar = false,
}: {
  tenant: string;
  workspace: string;
  /** In a phone's tab bar, across its width. */
  bar?: boolean;
}) {
  const params = { tenant, workspace };
  const { state } = useWorkspace();
  const onThread = useMatchRoute()({
    to: "/t/$tenant/w/$workspace/threads/$thread",
    params,
    fuzzy: true,
  });
  const open = Object.values(state.proposals).filter((proposal) => proposal.status === "open");
  return (
    <Tracks label="Workspace" {...(bar && { className: "flex-1" })}>
      <TrackLink
        icon={glyphs.messageSquare}
        render={
          <Link
            to="/t/$tenant/w/$workspace"
            params={params}
            activeOptions={{ exact: true, includeSearch: false }}
            {...(onThread && { "aria-current": "true" })}
          />
        }
      >
        Threads
      </TrackLink>
      <TrackLink
        icon={glyphs.fileText}
        render={<Link to="/t/$tenant/w/$workspace/artifacts" params={params} />}
      >
        Artifacts
      </TrackLink>
      <TrackLink
        icon={glyphs.workflow}
        count={open.length}
        render={<Link to="/t/$tenant/w/$workspace/proposals" params={params} />}
      >
        Proposals
      </TrackLink>
      <TrackLink
        icon={glyphs.play}
        render={<Link to="/t/$tenant/w/$workspace/runs" params={params} />}
      >
        Runs
      </TrackLink>
      <TrackLink
        icon={glyphs.zap}
        render={<Link to="/t/$tenant/w/$workspace/rules" params={params} />}
      >
        Rules
      </TrackLink>
    </Tracks>
  );
}

/**
 * What waits for the reader across the workspace, in the bar's corner (portalr ADR-0087): the
 * requests its paused turns hold, a link to the threads that hold them; nothing where none wait.
 */
function NeedYou({ tenant, workspace }: { tenant: string; workspace: string }) {
  const { state } = useWorkspace();
  const waiting = Object.values(state.runs)
    .filter((run) => run.status === "paused" && state.threads[run.threadId] !== undefined)
    .reduce((count, run) => count + run.requests.length, 0);
  const needs = waiting === 1 ? "needs" : "need";
  return (
    waiting > 0 && (
      <ButtonLink
        variant="ghost"
        size="sm"
        aria-label={`${waiting} ${needs} you`}
        render={
          <Link
            to="/t/$tenant/w/$workspace"
            params={{ tenant, workspace }}
            search={{ show: "needs" }}
          />
        }
      >
        <StatusBadge tone="waiting">
          {waiting}
          {/* On a phone, the count alone, named in full (portalr ADR-0087). */}
          <span className="max-sm:hidden"> {needs} you</span>
        </StatusBadge>
      </ButtonLink>
    )
  );
}
