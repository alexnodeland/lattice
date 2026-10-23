import { keys } from "@portalr/client";
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
import { useEffect, useId, useRef, useState } from "react";
import { opening, useNames } from "../../../../access";
import { type Level, levelOf } from "../../../../integrations";
import { ReadFailed } from "../../../../read-failed";
import {
  numberOf,
  refusedAs,
  type SettingRow,
  said,
  settersOf,
  settingRowsOf,
} from "../../../../settings";

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
        Settings are lowered here by a tenant's owners and admins. A workspace's admins lower their
        workspace's through grantr's API.
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

/** A level's settings, each lowered there. */
function LevelSettings({ tenant, workspace }: { tenant: string; workspace: string | undefined }) {
  const { queries } = Route.useRouteContext();
  const { data: view } = useSuspenseQuery(queries.grantr.settings(tenant, workspace));
  const inWorkspace = workspace !== undefined;
  const names = useNames(tenant, settersOf(view.settings, inWorkspace));
  const rows = settingRowsOf(view.settings, inWorkspace, names);
  return (
    <div className="flex flex-col gap-3">
      <Rows label={inWorkspace ? `Settings in ${workspace}` : "Settings on the tenant"}>
        {rows.map((row) =>
          // Kept by its key alone, so a change read back keeps what has the focus.
          row.kind.type === "int_range" ? (
            <Setting key={row.key} row={row} tenant={tenant} workspace={workspace} />
          ) : (
            // A setting of names is shown as it applies; it is changed through grantr's API
            // until this page has a field for it.
            <Row
              key={row.key}
              name={row.name}
              meta={`${row.description} Applies: ${row.effective}. Changed through grantr's API for now.`}
            />
          ),
        )}
      </Rows>
      {view.unknown.length > 0 && (
        <Alert tone="info">
          {`Also stored here, but no longer a setting, so never applied: ${view.unknown.join(", ")}.`}
        </Alert>
      )}
    </div>
  );
}

/** Why a change wasn't made, in words the field says, for each status grantr answers it with. */
function refusedWhy(row: SettingRow, status: number, reasons: readonly string[]): string {
  if (status === 403 || status === 422) {
    // Admins are told the ceiling and the layer that sets it, which they need to act on.
    return `${row.name} wasn't changed: ${refusedAs(reasons.join("; "), row)}`;
  }
  return `${row.name} wasn't changed: the server couldn't do it just now. Try again in a moment.`;
}

/**
 * Focus something of a row's, only where the reader hasn't moved on: from nowhere, or from within
 * the row's form; never from another row they have started on.
 */
function focusWithin(form: HTMLFormElement | null, target: HTMLElement | null) {
  const active = document.activeElement;
  if (active === null || active === document.body || form?.contains(active)) {
    target?.focus();
  }
}

/** One setting at a level: what applies and why, and a field to lower it, or unset it. */
function Setting({
  row,
  tenant,
  workspace,
}: {
  row: SettingRow;
  tenant: string;
  workspace: string | undefined;
}) {
  const { commands, queryClient, queries } = Route.useRouteContext();
  const shown = row.here === null ? "" : said(row.here.value);
  const [text, setText] = useState(shown);
  const [error, setErrorText] = useState<string | null>(null);
  // Each refusal is counted, so the same words again still take the field's focus, and are
  // read out again.
  const [refusals, setRefusals] = useState(0);
  const setError = (said: string | null) => {
    setErrorText(said);
    if (said !== null) {
      setRefusals((count) => count + 1);
    }
  };
  const [done, setDone] = useState("");
  const [stale, setStale] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const sending = useRef(false);
  const keepText = useRef(false);
  const field = useId();
  const warning = useRef<HTMLDivElement>(null);
  const form = useRef<HTMLFormElement>(null);
  // Read back at a new version, the field starts from what is set now, unless what was tried
  // is kept in it because someone changed it first.
  useEffect(() => {
    if (!keepText.current) {
      setText(shown);
    }
    keepText.current = false;
  }, [shown]);
  useEffect(() => {
    if (stale) {
      focusWithin(form.current, warning.current);
    }
  }, [stale]);
  useEffect(() => {
    if (refusals > 0) {
      focusWithin(form.current, document.getElementById(field));
    }
  }, [refusals, field]);

  /** Send a value, or unset with null, at the version read, once, and say what came of it. */
  async function send(value: number | null) {
    if (sending.current) {
      return;
    }
    sending.current = true;
    keepText.current = false;
    setSaving(true);
    setError(null);
    setStale(null);
    setDone("");
    try {
      await sent(value);
    } finally {
      sending.current = false;
      setSaving(false);
    }
  }

  /** What came of a send, said, with the setting read back. */
  async function sent(value: number | null) {
    const answer = await commands.grantr.setSetting(tenant, row.key, value, row.version, workspace);
    if (answer.outcome === "done") {
      setDone(`${row.name}: ${said(answer.result.effective)} applies.`);
      if (value === null) {
        // Its unset button goes once nothing is set here: the field keeps the focus instead.
        focusWithin(form.current, document.getElementById(field));
      }
    } else if (answer.status === 409) {
      keepText.current = true;
      await queryClient.invalidateQueries({ queryKey: keys.grantr.settings(tenant) });
      const now = queryClient
        .getQueryData(queries.grantr.settings(tenant, workspace).queryKey)
        ?.settings.find((state) => state.key === row.key);
      const here = workspace === undefined ? now?.tenant : now?.workspace;
      const tried = value === null ? "unset it" : `set ${value}`;
      setStale(
        `${row.name} was changed by someone else since you read it: ${
          here ? `it is set here to ${said(here.value)} now` : "nothing is set here now"
        }, and ${now ? said(now.effective) : "what it was"} applies. You tried to ${tried}, which wasn't saved: save again if you still want it.`,
      );
    } else {
      setError(refusedWhy(row, answer.status, answer.reasons));
    }
    if (answer.outcome === "done") {
      await queryClient.invalidateQueries({ queryKey: keys.grantr.settings(tenant) });
    }
  }

  const ceiling = typeof row.ceilingValue === "number" ? row.ceilingValue : 0;
  const low = row.low ?? 0;
  const lower = () => {
    const read = numberOf(text, low, row.high ?? ceiling);
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
          {row.clamped && <span>{row.clamped}</span>}
        </span>
      }
      end={
        <form
          ref={form}
          className="flex flex-col gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            lower();
          }}
        >
          {stale && (
            <div ref={warning} tabIndex={-1}>
              <Alert tone="warn">{stale}</Alert>
            </div>
          )}
          <TextField
            id={field}
            label={row.name}
            hint={`A whole number from ${low} to ${Math.max(low, ceiling)}.`}
            inputMode="numeric"
            value={text}
            onChange={(event) => setText(event.currentTarget.value)}
            error={error}
          />
          {/* There before anything is said, so what is said is announced as it changes. */}
          <p role="status" className="text-muted text-sm">
            {done}
          </p>
          <div className="flex flex-wrap gap-2">
            <Button type="submit" disabled={saving} focusableWhenDisabled>
              Save<span className="sr-only"> {row.name}</span>
            </Button>
            {row.here && (
              <Button
                variant="secondary"
                disabled={saving}
                focusableWhenDisabled
                onClick={() => void send(null)}
              >
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
