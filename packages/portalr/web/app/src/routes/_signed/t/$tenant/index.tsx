import { Account, Plain, Row, RowLink, Rows } from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";

/** The workspaces the caller can open in the tenant, as grantr lists them, in order. */
export const Route = createFileRoute("/_signed/t/$tenant/")({ component: Workspaces });

function Workspaces() {
  const { tenant } = Route.useParams();
  const { queries, signed } = Route.useRouteContext();
  const { data: me } = useSuspenseQuery(queries.grantr.me(tenant));
  const workspaces = [...me.workspaces].sort();
  return (
    <Plain home={<Link to="/" />} title={tenant} account={<Account signed={signed} />}>
      {workspaces.length === 0 ? (
        <p>There is no workspace here you can open.</p>
      ) : (
        <nav aria-label="Workspaces">
          <Rows label="Workspaces">
            {workspaces.map((workspace) => (
              <Row key={workspace}>
                <RowLink
                  render={<Link to="/t/$tenant/w/$workspace" params={{ tenant, workspace }} />}
                >
                  {workspace}
                </RowLink>
              </Row>
            ))}
          </Rows>
        </nav>
      )}
    </Plain>
  );
}
