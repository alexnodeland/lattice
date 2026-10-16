import type { Snapshot } from "@portalr/client";
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
          <div className="grid gap-3 sm:grid-cols-2 sm:max-w-xl">
            <SelectField
              label="Workspace"
              value={known ? workspace : ""}
              onChange={(event) =>
                void navigate({ search: shownOf({ ...search, workspace: event.target.value }) })
              }
              options={[
                ...(known ? [] : [{ value: "", label: "Choose a workspace" }]),
                ...names.map((name) => ({ value: name, label: name })),
              ]}
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
  const runs = listed(snapshot.state.runs, show);
  const parts: RunParts[] = runs.map((run) => ({
    key: run.id,
    name: `Run ${run.id}`,
    status: <RuleRunStatus status={run.status} />,
    title: <Title run={run} />,
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
 * a while, as it does while reflexr is down; or that it ended. Never what the server said: that
 * can echo what was sent.
 */
function Connection({ status }: { status: Snapshot<unknown>["status"] }) {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    setSlow(false);
    if (status === "live" || status === "closed") {
      return;
    }
    const timer = setTimeout(() => setSlow(true), PATIENCE);
    return () => clearTimeout(timer);
  }, [status]);
  if (status === "closed") {
    return (
      <p role="alert">The connection to this workspace ended. Reload the page to connect again.</p>
    );
  }
  if (status === "live") {
    return null;
  }
  return slow ? (
    <p role="alert">
      The workspace's runs can't be reached: reflexr may be down. It keeps trying, and they appear
      once it answers.
    </p>
  ) : (
    <p role="status">Reading the workspace's runs…</p>
  );
}

/** A run's rule, why it last failed, how often it was retried, and what people did to it. */
function Title({ run }: { run: Reflexr.Run }) {
  return (
    <div className="flex flex-col gap-1">
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
    confirm: "Cancel the run",
    body: "The run is stopped. If an attempt is running, what it gives is discarded, though what it already did outside isn't undone.",
  },
};

/**
 * A run's actions, each confirmed, and sent once. A retry makes the run something no list of
 * those needing attention holds, and a skip takes it from that list, so the button that opened the
 * dialog may be gone when it closes: focus then goes to the list's heading, and not to the page.
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
        name={`${WORDS[action].label} run ${run.id}`}
        title={WORDS[action].title}
        confirm={WORDS[action].confirm}
        calm={action === "retry"}
        {...(action === "retry" ? {} : { asking: "Reason (optional)" })}
        onOpenChange={(open) => {
          if (!open) {
            act.release(command(""));
          }
        }}
        onConfirm={async (reason) => {
          await act.send(command(reason));
          // After the dialog has closed, and focus has gone back where it can: if it can't, here.
          setTimeout(() => {
            if (!document.activeElement || document.activeElement === document.body) {
              heading.current?.focus();
            }
          }, FOCUS_AFTER);
        }}
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

/** How long after an action to look for where focus is: past the dialog's closing, in ms. */
const FOCUS_AFTER = 400;
