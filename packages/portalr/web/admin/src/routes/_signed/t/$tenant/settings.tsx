import { keys } from "@portalr/client";
import {
  Alert,
  Button,
  CheckboxGroup,
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
  notFound,
  type SearchSchemaInput,
} from "@tanstack/react-router";
import { useEffect, useId, useRef, useState } from "react";
import { useNames } from "../../../../access";
import type { Context } from "../../../../context";
import { type Level, levelOf } from "../../../../integrations";
import { ReadFailed } from "../../../../read-failed";
import {
  anywhere,
  MOST_ASKED,
  numberOf,
  type Places,
  refusedWhy,
  type SettingRow,
  said,
  settersOf,
  settingRowsOf,
  settingsPlaces,
} from "../../../../settings";

const title = "Settings";
const meta = "Limits a tenant or a workspace may lower, never raise, below the operator's";

/**
 * A tenant's settings, for whoever may narrow them somewhere in it: its owners and admins on the
 * tenant and in each workspace, a workspace's admins in theirs (issue 627). The level is chosen in the
 * address, of those the reader may narrow. Each setting is lowered or narrowed at that level,
 * never past the layer above, or set back to what it inherits; each says what applies, how far
 * this level may go and which layer says so, and what is set here and by whom (lattice
 * ADR-0030, portalr ADR-0067, ADR-0069).
 */
export const Route = createFileRoute("/_signed/t/$tenant/settings")({
  head: ({ params, match }) => ({
    meta: [{ title: match.context.title(`Settings · ${params.tenant}`) }],
  }),
  validateSearch: (search: Level & SearchSchemaInput): Level => levelOf(search),
  beforeLoad: async ({ context, params }) => {
    if (!anywhere(await placesIn(context, params.tenant))) {
      throw notFound();
    }
  },
  loaderDeps: ({ search }: { search: Level }) => ({ workspace: search.workspace }),
  loader: async ({ context, params, deps }) => {
    const { queries, queryClient } = context;
    const places = await placesIn(context, params.tenant);
    const level = levelIn(places, deps.workspace);
    if (level.mine) {
      await queryClient.ensureQueryData(queries.grantr.settings(params.tenant, level.workspace));
    }
  },
  component: SettingsPage,
  notFoundComponent: () => (
    <>
      <PageHeader title={title} meta={meta} />
      <EmptyState focus title="Settings aren't yours to change here">
        Settings are lowered by a tenant's owners and admins, and in a workspace by its admins.
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

/** Where the reader may narrow settings in the tenant: one read of grantr's checks, cached. */
async function placesIn(
  { queries, queryClient }: Pick<Context, "queries" | "queryClient">,
  tenant: string,
): Promise<Places> {
  const workspaces = await queryClient.ensureQueryData(queries.artifactr.workspaces(tenant));
  const asked = settingsPlaces(queries, tenant, workspaces);
  return asked.select(await queryClient.ensureQueryData(asked));
}

/**
 * The level shown: the one the address names, or with none named, the tenant, or for a
 * workspace's admin who may not narrow the tenant's, their first workspace; and whether it is
 * one the reader may narrow.
 */
function levelIn(places: Places, asked: string | undefined) {
  const workspace = asked ?? (places.tenant ? undefined : places.workspaces[0]);
  const mine = workspace === undefined ? places.tenant : places.workspaces.includes(workspace);
  return { workspace, mine };
}

/** The page: its level, chosen in the address of those the reader may narrow, and its settings. */
function SettingsPage() {
  const { tenant } = Route.useParams();
  const asked = Route.useSearch().workspace;
  const { queries } = Route.useRouteContext();
  const { data: workspaces } = useSuspenseQuery(queries.artifactr.workspaces(tenant));
  const { data: places } = useSuspenseQuery(settingsPlaces(queries, tenant, workspaces));
  const navigate = Route.useNavigate();
  const { workspace, mine } = levelIn(places, asked);
  const known = workspace === undefined || workspaces.includes(workspace);
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={title} meta={meta} focus />
      <SelectField
        label="Where"
        hint={
          places.tenant
            ? "A workspace may lower what the tenant allows, never raise it."
            : `The workspaces you administer. A workspace may lower what the tenant allows.${
                places.cut
                  ? ` Only the first ${MOST_ASKED} workspaces by name are checked here; a later one's settings are changed through grantr's API.`
                  : ""
              }`
        }
        className="max-w-sm"
        value={workspace ?? ""}
        onValueChange={(chosen) => void navigate({ search: levelOf({ workspace: chosen }) })}
        options={[
          ...(places.tenant ? [{ value: "", label: "The tenant" }] : []),
          ...(mine || workspace === undefined ? [] : [{ value: workspace, label: workspace }]),
          ...places.workspaces.map((name) => ({ value: name, label: `Workspace ${name}` })),
        ]}
      />
      {mine ? (
        <LevelSettings key={workspace ?? ""} tenant={tenant} workspace={workspace} />
      ) : known ? (
        <EmptyState title="Not a workspace you administer">
          You may change settings in the workspaces listed above. Choose one of them.
        </EmptyState>
      ) : (
        <EmptyState title="No such workspace">
          This tenant has no workspace by that name. Choose one of those listed above.
        </EmptyState>
      )}
    </div>
  );
}

/** A level's settings, each narrowed there. */
function LevelSettings({ tenant, workspace }: { tenant: string; workspace: string | undefined }) {
  const { queries } = Route.useRouteContext();
  const { data: view } = useSuspenseQuery(queries.grantr.settings(tenant, workspace));
  const inWorkspace = workspace !== undefined;
  const names = useNames(tenant, settersOf(view.settings, inWorkspace));
  const rows = settingRowsOf(view.settings, inWorkspace, names);
  return (
    <div className="flex flex-col gap-3">
      <Rows label={inWorkspace ? `Settings in ${workspace}` : "Settings on the tenant"}>
        {rows.map((row) => (
          // Kept by its key alone, so a change read back keeps what has the focus.
          <Setting key={row.key} row={row} tenant={tenant} workspace={workspace} />
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

/**
 * Focus something of a row's, only where the reader hasn't moved on: from nowhere, or from within
 * the row's form; never from another row they have started on.
 */
function focusWithin(form: HTMLFormElement | null, target: Element | null) {
  const active = document.activeElement;
  const free = active === null || active === document.body || form?.contains(active);
  if (free && target instanceof HTMLElement) {
    target.focus();
  }
}

/** A field's first control: the number's box, or the first box that may be checked. */
function controlOf(form: HTMLFormElement | null, field: string, subset: boolean) {
  return subset
    ? (form?.querySelector('[role="checkbox"]:not([data-disabled])') ?? null)
    : document.getElementById(field);
}

/** A setting's value as a change sends it: a number, names, or null to unset it. */
type Sent = number | readonly string[] | null;

/** What a field holds before it is sent: a number's text, or the names checked. */
type Draft = string | readonly string[];

/**
 * What a row's field starts from: what is set here, or, unset, what applies. A setting of names
 * starts from those the layer above still offers, so none is checked that can't be unchecked.
 */
function draftOf(row: SettingRow): Draft {
  const value = row.here?.value ?? row.effectiveValue;
  if (Array.isArray(value)) {
    const offered = new Set(Array.isArray(row.ceilingValue) ? row.ceilingValue : []);
    return value.filter((name) => offered.has(name));
  }
  return row.here === null ? "" : said(row.here.value);
}

/** A draft that holds for one version of a setting: what the reader typed, or kept after a 409. */
type Held = { readonly version: number; readonly draft: Draft } | null;

/** One setting at a level: what applies and why, and its field to narrow it, or unset it. */
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
  // What the field holds, for the version read: what the reader typed at it, or what they tried,
  // kept after someone else changed it first, at the version that came back; else what is set.
  const [edited, setEdited] = useState<Held>(null);
  const [kept, setKept] = useState<Held>(null);
  const draft =
    edited?.version === row.version
      ? edited.draft
      : kept?.version === row.version
        ? kept.draft
        : draftOf(row);
  const setDraft = (next: Draft) => setEdited({ version: row.version, draft: next });
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
  const field = useId();
  const warning = useRef<HTMLDivElement>(null);
  const form = useRef<HTMLFormElement>(null);
  const subset = row.kind.type === "subset";
  useEffect(() => {
    if (stale) {
      focusWithin(form.current, warning.current);
    }
  }, [stale]);
  useEffect(() => {
    if (refusals > 0) {
      focusWithin(form.current, controlOf(form.current, field, subset));
    }
  }, [refusals, field, subset]);

  /** Send a value, or unset with null, at the version read, once, and say what came of it. */
  async function send(value: Sent) {
    if (sending.current) {
      return;
    }
    sending.current = true;
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
  async function sent(value: Sent) {
    const answer = await commands.grantr.setSetting(tenant, row.key, value, row.version, workspace);
    if (answer.outcome === "done") {
      setDone(`${row.name}: ${said(answer.result.effective)} applies.`);
      if (value === null) {
        // Its unset button goes once nothing is set here: the field keeps the focus instead.
        focusWithin(form.current, controlOf(form.current, field, subset));
      }
    } else if (answer.status === 409) {
      const tried = draft;
      await queryClient.invalidateQueries({ queryKey: keys.grantr.settings(tenant) });
      const now = queryClient
        .getQueryData(queries.grantr.settings(tenant, workspace).queryKey)
        ?.settings.find((state) => state.key === row.key);
      if (now !== undefined) {
        setKept({ version: now.version, draft: tried });
      }
      const here = workspace === undefined ? now?.tenant : now?.workspace;
      const what = value === null ? "unset it" : `set ${said(value)}`;
      setStale(
        `${row.name} was changed by someone else since you read it: ${
          here ? `it is set here to ${said(here.value)} now` : "nothing is set here now"
        }, and ${now ? said(now.effective) : "what it was"} applies. You tried to ${what}, which wasn't saved: save again if you still want it.`,
      );
    } else {
      setError(refusedWhy(row, answer.status, typeof value === "number" ? value : null));
    }
    if (answer.outcome === "done") {
      await queryClient.invalidateQueries({ queryKey: keys.grantr.settings(tenant) });
    }
  }

  const ceiling = typeof row.ceilingValue === "number" ? row.ceilingValue : 0;
  const low = row.low ?? 0;
  const save = () => {
    if (typeof draft !== "string") {
      void send(draft);
      return;
    }
    const read = numberOf(draft, low, row.high ?? ceiling);
    if ("error" in read) {
      setError(read.error);
      return;
    }
    void send(read.value);
  };

  const allowed = new Set(Array.isArray(row.ceilingValue) ? row.ceilingValue : []);
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
            save();
          }}
        >
          {stale && (
            <div ref={warning} tabIndex={-1}>
              <Alert tone="warn">{stale}</Alert>
            </div>
          )}
          {typeof draft === "string" ? (
            <TextField
              id={field}
              label={row.name}
              hint={`A whole number from ${low} to ${Math.max(low, ceiling)}.`}
              inputMode="numeric"
              value={draft}
              onChange={(event) => setDraft(event.currentTarget.value)}
              error={error}
            />
          ) : (
            <CheckboxGroup
              legend={row.name}
              hint={`Checked tools are offered here. A tool ${row.ceilingBy} doesn't offer can't be checked.`}
              value={draft}
              onValueChange={setDraft}
              error={error}
              choices={(row.kind.universe ?? []).map((name) => {
                const risk = row.kind.labels?.[name];
                return {
                  value: name,
                  label: risk === undefined ? name : `${name} (${risk})`,
                  ...(allowed.has(name)
                    ? {}
                    : { disabled: true, description: `Not offered by ${row.ceilingBy}` }),
                };
              })}
            />
          )}
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
