import {
  AppShell,
  ButtonLink,
  type Glyph,
  glyphs,
  PageHeader,
  Row,
  RowLink,
  Rows,
  Switcher,
  TrackLink,
  Tracks,
} from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { AppAccount } from "../../../../analytics";

/**
 * The workspaces the caller can open in the tenant, as grantr lists them, in order, in the app's
 * frame, with the way to the approvals waiting for the reader in any of them: each a row whose
 * name opens its threads, and a compact track of its areas, each a link with its glyph, its word
 * beside it from the small breakpoint and its name alone below it, so five fit a phone's row
 * (portalr ADR-0085). Nothing is read per workspace; the frame's switcher names the tenant alone.
 */
export const Route = createFileRoute("/_signed/t/$tenant/")({
  head: ({ params, match }) => ({
    meta: [{ title: match.context.title(`Workspaces · ${params.tenant}`) }],
  }),
  loader: ({ context }) =>
    context.queryClient.ensureQueryData(context.queries.grantr.memberships(context.user)),
  component: Workspaces,
});

/** A workspace's areas, each a link from its card. */
const AREAS: readonly {
  readonly to:
    | "/t/$tenant/w/$workspace"
    | "/t/$tenant/w/$workspace/artifacts"
    | "/t/$tenant/w/$workspace/proposals"
    | "/t/$tenant/w/$workspace/runs"
    | "/t/$tenant/w/$workspace/rules";
  readonly label: string;
  readonly icon: Glyph;
}[] = [
  { to: "/t/$tenant/w/$workspace", label: "Threads", icon: glyphs.messageSquare },
  { to: "/t/$tenant/w/$workspace/artifacts", label: "Artifacts", icon: glyphs.fileText },
  { to: "/t/$tenant/w/$workspace/proposals", label: "Proposals", icon: glyphs.workflow },
  { to: "/t/$tenant/w/$workspace/runs", label: "Runs", icon: glyphs.play },
  { to: "/t/$tenant/w/$workspace/rules", label: "Rules", icon: glyphs.zap },
];

function Workspaces() {
  const { tenant } = Route.useParams();
  const { queries, user } = Route.useRouteContext();
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
      account={<AppAccount />}
    >
      <PageHeader
        title={tenant}
        actions={
          <ButtonLink
            variant="secondary"
            render={<Link to="/t/$tenant/approvals" params={{ tenant }} />}
          >
            Approvals
          </ButtonLink>
        }
      />
      {workspaces.length === 0 ? (
        <p>There is no workspace here you can open.</p>
      ) : (
        <Rows label="Workspaces">
          {workspaces.map((workspace) => (
            <Row
              key={workspace}
              name={
                <RowLink
                  render={<Link to="/t/$tenant/w/$workspace" params={{ tenant, workspace }} />}
                >
                  {workspace}
                </RowLink>
              }
              meta={
                <Tracks label={`${workspace}'s areas`} className="mt-1">
                  {AREAS.map(({ to, label, icon }) => (
                    <TrackLink
                      key={label}
                      icon={icon}
                      render={<Link to={to} params={{ tenant, workspace }} />}
                    >
                      {label}
                    </TrackLink>
                  ))}
                </Tracks>
              }
            />
          ))}
        </Rows>
      )}
    </AppShell>
  );
}
