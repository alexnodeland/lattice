import { allowedIn, type Reflexr, workspaceOf } from "@portalr/client";
import {
  ConfirmDialog,
  EmptyState,
  Moment,
  PageHeader,
  RuleRunStatus,
  RunList,
  type RunParts,
  SectionTitle,
  SelectField,
} from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import {
  createFileRoute,
  type ErrorComponentProps,
  type SearchSchemaInput,
} from "@tanstack/react-router";
import { opening } from "../../../../access";
import { ReadFailed } from "../../../../read-failed";
import { RunStreams, useAct, useRuns } from "../../../../run-streams";
import {
  type Action,
  actorName,
  commandFor,
  DONE,
  GRANTS,
  listed,
  offered,
  refusedAs,
  SHOWN,
  type Shown,
  shownOf,
} from "../../../../runs";

const HEADER = <PageHeader title="Runs" meta="The rules' runs in a workspace" />;

/**
 * A workspace's rule runs, live from reflexr's stream, for a tenant's owners and admins: those that
 * need someone, the dead-lettered and the retrying, or every one. Each may be retried, skipped or
 * cancelled where grantr allows, after a confirmation, once; and shows what people did to it. This
 * goes beyond RFC-0002's read-only row for admin (portalr ADR-0032).
 */
export const Route = createFileRoute("/_signed/t/$tenant/runs")({
  head: ({ params }) => ({ meta: [{ title: `Runs · ${params.tenant} · portalr admin` }] }),
  validateSearch: (search: Shown & SearchSchemaInput): Required<Shown> => shownOf(search),
  beforeLoad: ({ context, params }) => opening(context, params.tenant, "reflexr:read_runs"),
  loaderDeps: ({ search }: { search: Required<Shown> }) => ({ workspace: search.workspace }),
  // The tenant's workspaces, as artifactr lists them, and what may be done in the one shown.
  loader: async ({ context, params, deps }) => {
    const { queries, queryClient } = context;
    const workspaces = await queryClient.ensureQueryData(
      queries.artifactr.workspaces(params.tenant),
    );
    const shown = deps.workspace ?? [...workspaces].sort()[0];
    if (shown !== undefined) {
      await queryClient.ensureQueryData(
        allowedIn(queries, params.tenant, workspaceOf(shown), GRANTS),
      );
    }
  },
  component: RunsPage,
  notFoundComponent: () => (
    <>
      {HEADER}
      <EmptyState title="Runs aren't yours to see here">
        Runs are shown to a tenant's owners and admins.
      </EmptyState>
    </>
  ),
  errorComponent: ({ error, reset }: ErrorComponentProps) => (
    <ReadFailed title="Runs couldn't be read" header={HEADER} error={error} reset={reset} />
  ),
});

/** The page: its workspace and its list, chosen in the address. */
function RunsPage() {
  const { tenant } = Route.useParams();
  const search = Route.useSearch();
  const { queries } = Route.useRouteContext();
  const navigate = Route.useNavigate();
  const { data: workspaces } = useSuspenseQuery(queries.artifactr.workspaces(tenant));
  const names = [...workspaces].sort();
  const workspace = search.workspace ?? names[0];
  return (
    <div className="flex flex-col gap-6">
      {HEADER}
      {workspace === undefined ? (
        <EmptyState title="No workspaces">A tenant's rules run in its workspaces.</EmptyState>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2 sm:max-w-xl">
            <SelectField
              label="Workspace"
              value={workspace}
              onChange={(event) =>
                void navigate({ search: shownOf({ ...search, workspace: event.target.value }) })
              }
              options={(names.includes(workspace) ? names : [workspace, ...names]).map((name) => ({
                value: name,
                label: name,
              }))}
            />
            <SelectField
              label="Show"
              value={search.show}
              onChange={(event) =>
                void navigate({
                  search: shownOf({ ...search, workspace, show: event.target.value }),
                })
              }
              options={SHOWN.map((one) => ({ value: one.show, label: one.label }))}
            />
          </div>
          <DeadLetters />
          {/* Another tenant's or another workspace's is another page: its own stream, and nothing asked. */}
          <Workspace
            key={`${tenant}:${workspace}`}
            tenant={tenant}
            workspace={workspace}
            show={search.show}
          />
        </>
      )}
    </div>
  );
}

/** Which dead letters these are: there are others, which a person may have met. */
function DeadLetters() {
  return (
    <p className="max-w-prose text-muted text-sm">
      A dead-lettered run is a rule's run that failed every attempt. It is not the workspace's list
      of events a rule could not evaluate, nor the bridge's, which have their own.
    </p>
  );
}

function Workspace({
  tenant,
  workspace,
  show,
}: {
  tenant: string;
  workspace: string;
  show: "attention" | "all";
}) {
  const { config, signed } = Route.useRouteContext();
  return (
    <RunStreams surfaces={config.surfaces} signed={signed} tenant={tenant} workspace={workspace}>
      <Runs tenant={tenant} workspace={workspace} show={show} />
    </RunStreams>
  );
}

function Runs({
  tenant,
  workspace,
  show,
}: {
  tenant: string;
  workspace: string;
  show: "attention" | "all";
}) {
  const { queries } = Route.useRouteContext();
  const snapshot = useRuns();
  const { data: allowed } = useSuspenseQuery(
    allowedIn(queries, tenant, workspaceOf(workspace), GRANTS),
  );
  const runs = listed(snapshot.state.runs, show);
  const parts: RunParts[] = runs.map((run) => ({
    key: run.id,
    name: `Run ${run.id}`,
    status: <RuleRunStatus status={run.status} />,
    title: <Title run={run} />,
    attempts: run.attempt,
    feedback: null,
    actions: <Actions run={run} actions={offered(run.status, allowed)} />,
  }));
  return (
    <section aria-labelledby="runs" className="flex flex-col gap-3">
      <SectionTitle id="runs">Rules' runs in {workspace}</SectionTitle>
      <Connection status={snapshot.status} error={snapshot.error} />
      {snapshot.status === "live" && runs.length === 0 ? (
        <EmptyState title={show === "attention" ? "No run needs attention" : "No runs"}>
          {show === "attention"
            ? "A run that failed every attempt, or is waiting to try again, is shown here."
            : "A rule's run is shown when the rule fires."}
        </EmptyState>
      ) : (
        <RunList caption="Rules' runs" title="Rule" runs={parts} attempts feedback={false} />
      )}
    </section>
  );
}

/** Where the stream is, until it is live; or that it ended. */
function Connection({ status, error }: { status: string; error: string | null }) {
  if (status === "closed") {
    return (
      <p role="alert">
        The connection to this workspace ended{error ? `: ${error}` : ""}. Reload the page to
        connect again.
      </p>
    );
  }
  return status === "live" ? null : <p role="status">Reading the workspace's runs…</p>;
}

/** A run's rule, why it last failed, how often it was retried, and what people did to it. */
function Title({ run }: { run: Reflexr.Run }) {
  return (
    <span className="flex flex-col gap-1">
      <code className="font-mono">{run.rule}</code>
      {run.reason && <span className="text-muted text-xs">last failure: {run.reason}</span>}
      {run.retries > 0 && (
        <span className="text-muted text-xs">
          retried {run.retries === 1 ? "once" : `${run.retries} times`}
        </span>
      )}
      {run.history.length > 0 && (
        <details className="text-xs">
          <summary className="cursor-pointer text-muted">History ({run.history.length})</summary>
          <ul className="mt-1 flex flex-col gap-1">
            {run.history.map((step) => (
              <li key={`${step.at}-${step.kind}`}>
                {actorName(step.actor)} {DONE[step.kind]} <Moment at={step.at} />
                {step.reason ? <span className="text-muted">: {step.reason}</span> : null}
              </li>
            ))}
          </ul>
        </details>
      )}
    </span>
  );
}

const WORDS: Record<Action, { label: string; title: string; confirm: string; body: string }> = {
  retry: {
    label: "Retry",
    title: "Retry this run?",
    confirm: "Retry the run",
    body: "It runs again now, with a fresh set of attempts. If its action changes something outside, it changes it again.",
  },
  skip: {
    label: "Skip",
    title: "Skip this run?",
    confirm: "Skip the run",
    body: "The run is given up on, and the runs of its scope that wait behind it can go on. It isn't run again unless someone retries it.",
  },
  cancel: {
    label: "Cancel",
    title: "Cancel this run?",
    confirm: "Cancel the run",
    body: "The run is stopped. If an attempt is running, what it gives is discarded, though what it already did outside isn't undone.",
  },
};

/** A run's actions, each confirmed, and sent once. */
function Actions({ run, actions }: { run: Reflexr.Run; actions: Action[] }) {
  const act = useAct(refusedAs);
  return actions.map((action) => (
    <ConfirmDialog
      key={action}
      label={WORDS[action].label}
      name={`${WORDS[action].label} run ${run.id}`}
      title={WORDS[action].title}
      confirm={WORDS[action].confirm}
      calm={action === "retry"}
      {...(action === "retry" ? {} : { asking: "Reason (optional)" })}
      onConfirm={(reason) => act(commandFor(action, run.id, reason))}
    >
      <p>
        <code className="font-mono">{run.rule}</code>, {run.id}: attempt {run.attempt}
        {run.reason ? `, last failure ${run.reason}` : ""}.
      </p>
      <p>{WORDS[action].body}</p>
    </ConfirmDialog>
  ));
}
