import type { Snapshot } from "@portalr/client";
import { allowedIn, filedBy, type Reflexr, type TrackerItem, workspaceOf } from "@portalr/client";
import {
  Alert,
  ConfirmDialog,
  EmptyState,
  Moment,
  PageHeader,
  Reading,
  RuleRunStatus,
  RunList,
  type RunParts,
  SectionTitle,
  SegmentedFilter,
  SelectField,
  TrackerItems,
} from "@portalr/ui";
import { useQuery, useSuspenseQuery } from "@tanstack/react-query";
import {
  createFileRoute,
  type ErrorComponentProps,
  type SearchSchemaInput,
} from "@tanstack/react-router";
import { type RefObject, useEffect, useRef, useState } from "react";
import { opening } from "../../../../access";
import { ReadFailed } from "../../../../read-failed";
import { RunStreams, useAct, useRuns } from "../../../../run-streams";
import {
  type Action,
  actorName,
  commandFor,
  DONE,
  firstOf,
  GRANTS,
  listed,
  offered,
  PATIENCE,
  refusedAs,
  SHOWN,
  type Show,
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
  head: ({ params, match }) => ({
    meta: [{ title: match.context.title(`Runs · ${params.tenant}`) }],
  }),
  validateSearch: (search: Shown & SearchSchemaInput): Required<Shown> => shownOf(search),
  beforeLoad: ({ context, params }) => opening(context, params.tenant, "reflexr:read_runs"),
  loaderDeps: ({ search }: { search: Required<Shown> }) => ({ workspace: search.workspace }),
  // The tenant's workspaces, as artifactr lists them, and what may be done in the one shown.
  loader: async ({ context, params, deps }) => {
    const { queries, queryClient } = context;
    const workspaces = await queryClient.ensureQueryData(
      queries.artifactr.workspaces(params.tenant),
    );
    const shown = deps.workspace ?? firstOf(workspaces);
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
  const workspace = search.workspace ?? firstOf(workspaces);
  const known = workspace !== undefined && names.includes(workspace);
  return (
    <div className="flex flex-col gap-6">
      {HEADER}
      {workspace === undefined ? (
        <EmptyState title="No workspaces">A tenant's rules run in its workspaces.</EmptyState>
      ) : (
        <>
          <div className="grid items-start gap-3 sm:grid-cols-2">
            <SelectField
              label="Workspace"
              value={known ? workspace : ""}
              onValueChange={(chosen) =>
                void navigate({ search: shownOf({ ...search, workspace: chosen }) })
              }
              options={[
                ...(known ? [] : [{ value: "", label: "Choose a workspace" }]),
                ...names.map((name) => ({ value: name, label: name })),
              ]}
            />
            <SegmentedFilter
              label="Show"
              showLabel
              segments={SHOWN.map((one) => ({ value: one.show, label: one.label }))}
              value={search.show}
              onValueChange={(show) =>
                void navigate({ search: shownOf({ ...search, workspace, show }) })
              }
            />
          </div>
          <DeadLetters />
          {known ? (
            <Workspace tenant={tenant} workspace={workspace} show={search.show} />
          ) : (
            <EmptyState title="No such workspace">
              This tenant has no workspace by that name. Choose one of its own.
            </EmptyState>
          )}
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

function Workspace({ tenant, workspace, show }: { tenant: string; workspace: string; show: Show }) {
  const { config, signed } = Route.useRouteContext();
  return (
    <RunStreams surfaces={config.surfaces} signed={signed} tenant={tenant} workspace={workspace}>
      <Runs tenant={tenant} workspace={workspace} show={show} />
    </RunStreams>
  );
}

function Runs({ tenant, workspace, show }: { tenant: string; workspace: string; show: Show }) {
  const { queries } = Route.useRouteContext();
  const snapshot = useRuns();
  const heading = useRef<HTMLHeadingElement>(null);
  const { data: allowed } = useSuspenseQuery(
    allowedIn(queries, tenant, workspaceOf(workspace), GRANTS),
  );
  const { data: filed } = useQuery(queries.relayr.filed(tenant, workspace));
  const runs = listed(snapshot.state.runs, show);
  const parts: RunParts[] = runs.map((run) => ({
    key: run.id,
    name: `Run ${run.id}`,
    status: <RuleRunStatus status={run.status} />,
    title: <Title run={run} filed={filedBy(filed, run.chain)} />,
    attempts: run.attempt,
    feedback: null,
    actions: <Actions run={run} actions={offered(run.status, allowed)} heading={heading} />,
  }));
  return (
    <section aria-labelledby="runs" className="flex flex-col gap-3">
      <SectionTitle id="runs" tabIndex={-1} ref={heading}>
        Rules' runs in {workspace}
      </SectionTitle>
      <Connection status={snapshot.status} />
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

/**
 * Where the stream is, until it is live; that it can't get through, if it has been connecting for
 * a while, as it does while reflexr is down; or that it ended. A replay, which can take as long as
 * the log is long, is reading, not a failure. Never what the server said: that can echo what was
 * sent.
 */
function Connection({ status }: { status: Snapshot<unknown>["status"] }) {
  switch (status) {
    case "live":
      return null;
    case "closed":
      return (
        <Alert tone="error">
          The connection to this workspace ended. Reload the page to connect again.
        </Alert>
      );
    case "replaying":
      return <Reading>Reading the workspace's runs…</Reading>;
    case "connecting":
      // Mounted for as long as it connects, so its wait starts over with each connecting.
      return <Connecting />;
  }
}

/** Connecting: reading, and, past `PATIENCE` without an answer, that it can't be reached. */
function Connecting() {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setSlow(true), PATIENCE);
    return () => clearTimeout(timer);
  }, []);
  return slow ? (
    <Alert tone="error">
      The workspace's runs can't be reached: reflexr may be down. It keeps trying, and they appear
      once it answers.
    </Alert>
  ) : (
    <Reading>Reading the workspace's runs…</Reading>
  );
}

/**
 * A run's rule, why it last failed, how often it was retried, the tracker items its chain filed,
 * and what people did to it.
 */
function Title({ run, filed }: { run: Reflexr.Run; filed: readonly TrackerItem[] }) {
  return (
    <div className="flex flex-col gap-1">
      <code className="font-mono">{run.rule}</code>
      {run.reason && <span className="text-muted text-xs">last failure: {run.reason}</span>}
      {run.retries > 0 && (
        <span className="text-muted text-xs">
          retried {run.retries === 1 ? "once" : `${run.retries} times`}
        </span>
      )}
      <TrackerItems label="Filed as" items={filed} />
      {run.history.length > 0 && (
        <details className="text-xs">
          <summary
            aria-label={`History of run ${run.id}, ${run.history.length}`}
            className="cursor-pointer text-muted"
          >
            History ({run.history.length})
          </summary>
          <ul className="mt-1 flex flex-col gap-1">
            {run.history.map((step) => (
              <li key={step.seq}>
                {actorName(step.actor)} {DONE[step.kind]} <Moment at={step.at} />
                {step.reason ? <span className="text-muted">: {step.reason}</span> : null}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
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
    confirm: "Cancel run",
    body: "The run is stopped. If an attempt is running, what it gives is discarded, though what it already did outside isn't undone.",
  },
};

/**
 * A run's actions, each confirmed, and sent once. A retry makes the run something the list of
 * those needing attention doesn't hold, and a skip takes it from that list, so the button that
 * opened the dialog goes, and the dialog with it: focus then goes to the list's heading, and not
 * to the page.
 */
function Actions({
  run,
  actions,
  heading,
}: {
  run: Reflexr.Run;
  actions: Action[];
  heading: RefObject<HTMLElement | null>;
}) {
  const act = useAct(refusedAs);
  return actions.map((action) => {
    const command = (reason: string) => commandFor(action, run.id, reason);
    return (
      <ConfirmDialog
        key={action}
        label={WORDS[action].label}
        about={`run ${run.id}`}
        look={action === "cancel" ? "danger-soft" : "ghost"}
        size="sm"
        {...(action === "cancel" && { dismiss: "Keep running" })}
        title={WORDS[action].title}
        confirm={WORDS[action].confirm}
        calm={action === "retry"}
        {...(action === "retry" ? {} : { asking: "Reason (optional)" })}
        returnTo={heading}
        onOpenChange={(open) => {
          if (!open) {
            act.release(command(""));
          }
        }}
        onConfirm={(reason) => act.send(command(reason))}
      >
        <p>
          <code className="font-mono">{run.rule}</code>, {run.id}: attempt {run.attempt}
          {run.reason ? `, last failure ${run.reason}` : ""}.
        </p>
        <p>{WORDS[action].body}</p>
      </ConfirmDialog>
    );
  });
}
