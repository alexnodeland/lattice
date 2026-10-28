import { changedIntegrations, deploymentAt, refusal } from "@portalr/client";
import {
  Alert,
  EmptyState,
  IntegrationList,
  type IntegrationRow,
  PageHeader,
  SelectField,
  TextLink,
} from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import {
  createFileRoute,
  type ErrorComponentProps,
  Link,
  type SearchSchemaInput,
} from "@tanstack/react-router";
import { useState } from "react";
import { opening, type Said, useAccess, useNames } from "../../../../access";
import { type Level, levelOf, rowsOf, settersOf } from "../../../../integrations";
import { ReadFailed } from "../../../../read-failed";

const HEADER = (
  <PageHeader
    title="Integrations"
    meta="What the tenant and each workspace offer beyond the basics"
  />
);

/**
 * A tenant's integrations, for whoever may switch them there: on the tenant, or in one of its
 * workspaces, chosen in the address. Each is switched on or off at that level, or set back to
 * what it inherits, and says where its state comes from and who set it there. A workspace can't
 * turn on what the tenant turned off, nor anything the deployment doesn't install (grantr
 * ADR-0034, portalr ADR-0045).
 */
export const Route = createFileRoute("/_signed/t/$tenant/integrations")({
  head: ({ params, match }) => ({
    meta: [{ title: match.context.title(`Integrations · ${params.tenant}`) }],
  }),
  validateSearch: (search: Level & SearchSchemaInput): Level => levelOf(search),
  beforeLoad: ({ context, params }) =>
    opening(context, params.tenant, "grantr:manage_integrations"),
  loaderDeps: ({ search }: { search: Level }) => ({ workspace: search.workspace }),
  // The tenant's workspaces, as artifactr lists them, and the integrations at the level shown.
  loader: async ({ context, params, deps }) => {
    const { queries, queryClient } = context;
    const workspaces = await queryClient.ensureQueryData(
      queries.artifactr.workspaces(params.tenant),
    );
    if (deps.workspace === undefined || workspaces.includes(deps.workspace)) {
      await queryClient.ensureQueryData(queries.grantr.integrations(params.tenant, deps.workspace));
    }
  },
  component: IntegrationsPage,
  notFoundComponent: () => (
    <>
      {HEADER}
      <EmptyState focus title="Integrations aren't yours to switch here">
        Integrations are switched by a tenant's owners and admins.
      </EmptyState>
    </>
  ),
  errorComponent: ({ error, reset }: ErrorComponentProps) => (
    <ReadFailed title="Integrations couldn't be read" header={HEADER} error={error} reset={reset} />
  ),
});

/** The page: its level, chosen in the address, and that level's integrations. */
function IntegrationsPage() {
  const { tenant } = Route.useParams();
  const { workspace } = Route.useSearch();
  const { queries } = Route.useRouteContext();
  const navigate = Route.useNavigate();
  const { data: workspaces } = useSuspenseQuery(queries.artifactr.workspaces(tenant));
  const names = [...workspaces].sort();
  const known = workspace === undefined || names.includes(workspace);
  return (
    <div className="flex flex-col gap-6">
      {HEADER}
      <SelectField
        label="Where"
        hint="A workspace inherits the tenant's settings, and can't turn on what the tenant turned off."
        className="max-w-sm"
        value={workspace ?? ""}
        onValueChange={(chosen) => void navigate({ search: levelOf({ workspace: chosen }) })}
        options={[
          { value: "", label: "The tenant" },
          ...(workspace === undefined || known ? [] : [{ value: workspace, label: workspace }]),
          ...names.map((name) => ({ value: name, label: `Workspace ${name}` })),
        ]}
      />
      {known ? (
        <Settings key={workspace ?? ""} tenant={tenant} workspace={workspace} />
      ) : (
        <EmptyState title="No such workspace">
          This tenant has no workspace by that name. Choose the tenant, or one of its workspaces.
        </EmptyState>
      )}
    </div>
  );
}

/** A level's integrations, each switched there, and what the last change said. */
function Settings({ tenant, workspace }: { tenant: string; workspace: string | undefined }) {
  const { queries, commands, queryClient, config } = Route.useRouteContext();
  const { allowed } = useAccess(tenant);
  const { data: states } = useSuspenseQuery(queries.grantr.integrations(tenant, workspace));
  const inWorkspace = workspace !== undefined;
  const names = useNames(tenant, settersOf(states, inWorkspace));
  // Each app an integration brings, at its address beside the portal's this page is at.
  const rows = rowsOf(states, inWorkspace, names, deploymentAt(config, location.origin).links);
  const [saving, setSaving] = useState<ReadonlySet<string>>(new Set());
  const [said, setSaid] = useState<Said>(null);
  const place = inWorkspace ? `in ${workspace}` : "on the tenant";

  /** Set an integration at this level, or unset it with null, once, and say what came of it. */
  async function set(row: IntegrationRow, on: boolean | null) {
    setSaving((now) => new Set(now).add(row.key));
    setSaid(null);
    const answer = await changedIntegrations(
      queryClient,
      tenant,
      commands.grantr.setIntegration(tenant, row.key, on, workspace),
    );
    setSaving((now) => new Set([...now].filter((key) => key !== row.key)));
    if (answer.outcome === "refused") {
      setSaid({ said: refusal(`${row.name} wasn't changed`, answer), refused: true });
      return;
    }
    const now = answer.result.enabled ? "on" : "off";
    setSaid({
      said:
        on === null
          ? `${row.name} is back to ${inWorkspace ? "the tenant's" : "its default"} ${place}: ${now}.`
          : `${row.name} is ${now} ${place}.`,
      refused: false,
    });
  }

  const byKey = new Map(rows.map((row) => [row.key, row]));
  const act = (key: string, on: boolean | null) => {
    const row = byKey.get(key);
    if (row) {
      void set(row, on);
    }
  };
  return (
    <div className="flex flex-col gap-3">
      {said && <Alert tone={said.refused ? "error" : "info"}>{said.said}</Alert>}
      <IntegrationList
        caption={inWorkspace ? `Integrations in ${workspace}` : "Integrations on the tenant"}
        level={inWorkspace ? "workspace" : "tenant"}
        rows={rows}
        saving={saving}
        onSwitch={act}
        onInherit={(key) => act(key, null)}
        history={(row) =>
          row.changed &&
          allowed.has("grantr:read_audit") && (
            <TextLink
              variant="subtle"
              render={
                <Link
                  to="/t/$tenant/audit"
                  params={{ tenant }}
                  search={{ type: "integration_set" }}
                />
              }
            >
              See the audit log<span className="sr-only"> for {row.name}</span>
            </TextLink>
          )
        }
      />
    </div>
  );
}
