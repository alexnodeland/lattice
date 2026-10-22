import { keys, refusal } from "@portalr/client";
import {
  Alert,
  Button,
  EmptyState,
  PageHeader,
  Row,
  Rows,
  SelectField,
  TextField,
} from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import {
  createFileRoute,
  type ErrorComponentProps,
  type SearchSchemaInput,
} from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { opening, useNames } from "../../../../access";
import { type Level, levelOf } from "../../../../integrations";
import { ReadFailed } from "../../../../read-failed";
import { numberOf, type SettingRow, said, settersOf, settingRowsOf } from "../../../../settings";

const title = "Settings";
const meta = "Limits a tenant or a workspace may lower, never raise, below the operator's";

/**
 * A tenant's settings, for whoever may narrow them there: on the tenant, or in one of its
 * workspaces, chosen in the address. Each is lowered at that level, never above the layer above,
 * or set back to what it inherits; each says what applies, how far this level may go and which
 * layer says so, and what is set here and by whom (lattice ADR-0030, portalr ADR-0067).
 */
export const Route = createFileRoute("/_signed/t/$tenant/settings")({
  head: ({ params, match }) => ({
    meta: [{ title: match.context.title(`Settings · ${params.tenant}`) }],
  }),
  validateSearch: (search: Level & SearchSchemaInput): Level => levelOf(search),
  beforeLoad: ({ context, params }) => opening(context, params.tenant, "grantr:manage_settings"),
  loaderDeps: ({ search }: { search: Level }) => ({ workspace: search.workspace }),
  loader: async ({ context, params, deps }) => {
    const { queries, queryClient } = context;
    const workspaces = await queryClient.ensureQueryData(
      queries.artifactr.workspaces(params.tenant),
    );
    if (deps.workspace === undefined || workspaces.includes(deps.workspace)) {
      await queryClient.ensureQueryData(queries.grantr.settings(params.tenant, deps.workspace));
    }
  },
  component: SettingsPage,
  notFoundComponent: () => (
    <>
      <PageHeader title={title} meta={meta} />
      <EmptyState focus title="Settings aren't yours to change here">
        Settings are lowered by a tenant's owners and admins, and a workspace's admins.
      </EmptyState>
    </>
  ),
  errorComponent: ({ error, reset }: ErrorComponentProps) => (
    <ReadFailed
      title="Settings couldn't be read"
      header={<PageHeader title={title} meta={meta} />}
      error={error}
      reset={reset}
    />
  ),
});

/** The page: its level, chosen in the address, and that level's settings. */
function SettingsPage() {
  const { tenant } = Route.useParams();
  const { workspace } = Route.useSearch();
  const { queries } = Route.useRouteContext();
  const navigate = Route.useNavigate();
  const { data: workspaces } = useSuspenseQuery(queries.artifactr.workspaces(tenant));
  const names = [...workspaces].sort();
  const known = workspace === undefined || names.includes(workspace);
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={title} meta={meta} focus />
      <SelectField
        label="Where"
        hint="A workspace may lower what the tenant allows, never raise it."
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
        <LevelSettings key={workspace ?? ""} tenant={tenant} workspace={workspace} />
      ) : (
        <EmptyState title="No such workspace">
          This tenant has no workspace by that name. Choose the tenant, or one of its workspaces.
        </EmptyState>
      )}
    </div>
  );
}

/** What came of a change to a setting: what applies now, or that someone changed it first. */
type Notice = { readonly said: string; readonly stale: boolean };

/** A level's settings, each lowered there, and what the last change to each said. */
function LevelSettings({ tenant, workspace }: { tenant: string; workspace: string | undefined }) {
  const { queries } = Route.useRouteContext();
  const { data: view } = useSuspenseQuery(queries.grantr.settings(tenant, workspace));
  const inWorkspace = workspace !== undefined;
  const names = useNames(tenant, settersOf(view.settings, inWorkspace));
  const rows = settingRowsOf(view.settings, inWorkspace, names);
  const [notices, setNotices] = useState<Readonly<Record<string, Notice>>>({});
  return (
    <div className="flex flex-col gap-3">
      <Rows label={inWorkspace ? `Settings in ${workspace}` : "Settings on the tenant"}>
        {rows.map((row) => (
          // Read again at a new version, a setting's field starts from what is set now.
          <Setting
            key={`${row.key}@${row.version}`}
            row={row}
            tenant={tenant}
            workspace={workspace}
            notice={notices[row.key] ?? null}
            told={(notice) => setNotices((now) => ({ ...now, [row.key]: notice }))}
          />
        ))}
      </Rows>
      {view.unknown.length > 0 && (
        <Alert tone="info">
          {`Also stored here, but no longer a setting, so never applied: ${view.unknown.join(", ")}.`}
        </Alert>
      )}
    </div>
  );
}

/** One setting at a level: what applies and why, and a field to lower it, or unset it. */
function Setting({
  row,
  tenant,
  workspace,
  notice,
  told,
}: {
  row: SettingRow;
  tenant: string;
  workspace: string | undefined;
  notice: Notice | null;
  told: (notice: Notice) => void;
}) {
  const { commands, queryClient } = Route.useRouteContext();
  const [text, setText] = useState(row.here === null ? "" : said(row.here.value));
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const alert = useRef<HTMLDivElement>(null);
  useEffect(() => {
    // A change someone made first is said where the reader is, with the setting as it is now.
    if (notice?.stale) {
      alert.current?.focus();
    }
  }, [notice]);

  /** Send a value, or unset with null, at the version read, and say what came of it. */
  async function send(value: number | null) {
    setSaving(true);
    setError(null);
    const answer = await commands.grantr.setSetting(tenant, row.key, value, row.version, workspace);
    setSaving(false);
    if (answer.outcome === "done") {
      told({ said: `${row.name}: ${said(answer.result.effective)} applies.`, stale: false });
    } else if (answer.status === 409) {
      told({
        said: `${row.name} was changed by someone else since you read it, and is shown as it is now. Make your change again if you still want it.`,
        stale: true,
      });
    } else {
      setError(refusal(`${row.name} wasn't changed`, answer));
      return;
    }
    await queryClient.invalidateQueries({ queryKey: keys.grantr.settings(tenant) });
  }

  const lower = () => {
    const read = numberOf(text, row.kind);
    if ("error" in read) {
      setError(read.error);
      return;
    }
    void send(read.value);
  };

  return (
    <Row
      name={row.name}
      meta={
        <span className="flex flex-col gap-0.5">
          <span>{row.description}</span>
          <span>{`Applies: ${row.effective}. ${row.ceiling}`}</span>
          {row.here && (
            <span>{`Set here to ${said(row.here.value)} by ${row.here.by}, ${new Date(row.here.at).toLocaleString()}.`}</span>
          )}
          {row.clamped && (
            <span>{`What is set here doesn't apply: ${row.effective} does, as no more is allowed now.`}</span>
          )}
        </span>
      }
      end={
        <form
          className="flex flex-col gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            lower();
          }}
        >
          {notice && (
            <div ref={alert} tabIndex={-1}>
              <Alert tone={notice.stale ? "warn" : "info"}>{notice.said}</Alert>
            </div>
          )}
          <TextField
            label={row.name}
            hint={`A whole number, at most ${said(row.ceilingValue)}.`}
            inputMode="numeric"
            value={text}
            onChange={(event) => setText(event.currentTarget.value)}
            error={error}
          />
          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={saving}>
              Save<span className="sr-only"> {row.name}</span>
            </Button>
            {row.here && (
              <Button variant="secondary" disabled={saving} onClick={() => void send(null)}>
                {`Use ${row.inherits}`}
                <span className="sr-only"> for {row.name}</span>
              </Button>
            )}
          </div>
        </form>
      }
    />
  );
}
