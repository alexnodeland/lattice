import { allowedIn, filedBy, thumbs, useMe, workspaceOf } from "@portalr/client";
import {
  CommandButton,
  Moment,
  PageHeader,
  RuleRunStatus,
  RunList,
  type RunParts,
  RunStatus,
  SectionTitle,
  TextLink,
  Thumbs,
  TrackerItems,
} from "@portalr/ui";
import { useQuery, useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useMemo } from "react";
import {
  Connection,
  useAutomation,
  useAutomationStream,
  useStream,
  useWorkspace,
} from "../../../../../../workspace";

/** What a person may do with a run, as grantr answers for the workspace. */
const ACTIONS = [
  "artifactr:stop_run",
  "artifactr:give_feedback",
  "reflexr:retry_run",
  "reflexr:skip_run",
  "reflexr:cancel_run",
  "reflexr:give_feedback",
] as const;

/**
 * The workspace's runs: artifactr's turns, each with its thread, and reflexr's rule runs, the
 * dead-lettered marked, newest first. Each offers what its library does with a run, where grantr
 * allows: a running turn stops (artifactr can stop no other); a rule run retries, is skipped or is
 * cancelled, by its status, a queued one only cancelled. A rule run links to the tracker items its
 * chain filed, and to those whose changes fired it (lattice RFC-0004).
 */
export const Route = createFileRoute("/_signed/t/$tenant/w/$workspace/runs")({
  head: ({ params, match }) => ({
    meta: [{ title: match.context.title(`Runs · ${params.workspace}`) }],
  }),
  loader: ({ context, params }) =>
    context.queryClient.ensureQueryData(
      allowedIn(context.queries, params.tenant, workspaceOf(params.workspace), ACTIONS),
    ),
  component: Runs,
});

/** Whether a moment is one a `Date` reads. */
const readable = (at: string | undefined): at is string =>
  at !== undefined && !Number.isNaN(Date.parse(at));

/** Runs, the newest first. */
const newest = <R extends { started: number }>(runs: Readonly<Record<string, R>>) =>
  Object.values(runs).sort((a, b) => b.started - a.started);

function Runs() {
  const { tenant, workspace } = Route.useParams();
  const { queries, user } = Route.useRouteContext();
  const me = useMe(queries, user, tenant);
  const checks = useMemo(
    () => allowedIn(queries, tenant, workspaceOf(workspace), ACTIONS),
    [queries, tenant, workspace],
  );
  const { data: allowed } = useSuspenseQuery(checks);
  const turns = useWorkspace();
  const automation = useAutomation();
  const artifactr = useStream();
  const reflexr = useAutomationStream();
  const turnRuns = useMemo(() => newest(turns.state.runs), [turns.state.runs]);
  const ruleRuns = useMemo(() => newest(automation.state.runs), [automation.state.runs]);
  // What the runs filed in a tracker, which a run's end reads again; none where there's no tracker.
  const { data: filed } = useQuery(queries.relayr.filed(tenant, workspace));
  const turnFeedback = allowed.has("artifactr:give_feedback");
  const runFeedback = allowed.has("reflexr:give_feedback");

  const turnParts: RunParts[] = turnRuns.map((run) => ({
    key: run.id,
    name: `Turn ${run.id}`,
    status: <RunStatus status={run.status} />,
    title: (
      <span data-portalr-replay="block">
        <TextLink
          variant="subtle"
          render={
            <Link
              to="/t/$tenant/w/$workspace/threads/$thread"
              params={{ tenant, workspace, thread: run.threadId }}
            />
          }
        >
          {turns.state.threads[run.threadId]?.title || "Untitled"}
        </TextLink>
      </span>
    ),
    // A start the log gave no readable time for is left blank, never "Invalid Date".
    started: readable(run.startedAt) && <Moment at={run.startedAt} />,
    feedback: turnFeedback && (
      <span data-portalr-replay="block">
        <Thumbs
          given={thumbs(run.feedback, me)}
          onThumbs={(up, comment) =>
            artifactr.send({
              type: "give_feedback",
              feedback_type: "thumbs",
              target: { kind: "turn", run_id: run.id },
              value: comment === null ? { up } : { up, comment },
            })
          }
        />
      </span>
    ),
    actions: run.status === "running" && allowed.has("artifactr:stop_run") && (
      <CommandButton onSend={() => artifactr.send({ type: "stop_run", run_id: run.id })}>
        Stop
      </CommandButton>
    ),
  }));

  const ruleParts: RunParts[] = ruleRuns.map((run) => {
    const retry = run.status === "dead_lettered" && allowed.has("reflexr:retry_run");
    const skip =
      (run.status === "dead_lettered" || run.status === "retrying") &&
      allowed.has("reflexr:skip_run");
    const cancel =
      (run.status === "pending" || run.status === "running" || run.status === "retrying") &&
      allowed.has("reflexr:cancel_run");
    return {
      key: run.id,
      name: `Run ${run.id}`,
      status: <RuleRunStatus status={run.status} />,
      title: (
        <span className="flex flex-col" data-portalr-replay="block">
          <code className="font-mono">{run.rule}</code>
          {run.retries > 0 && (
            <span className="text-muted text-xs">
              retried {run.retries === 1 ? "once" : `${run.retries} times`}
            </span>
          )}
          <TrackerItems label="From" items={automation.state.firedBy[run.id] ?? []} />
          <TrackerItems label="Filed as" items={filedBy(filed, run.chain)} />
        </span>
      ),
      attempts: run.attempt,
      feedback: runFeedback && (
        <span data-portalr-replay="block">
          <Thumbs
            given={thumbs(run.feedback, me)}
            onThumbs={(up, comment) =>
              reflexr.send({
                type: "give_feedback",
                feedback_type: "thumbs",
                target: { kind: "run", run_id: run.id },
                value: comment === null ? { up } : { up, comment },
              })
            }
          />
        </span>
      ),
      actions: (retry || skip || cancel) && (
        <>
          {retry && (
            <CommandButton onSend={() => reflexr.send({ type: "retry_run", run_id: run.id })}>
              Retry
            </CommandButton>
          )}
          {skip && (
            <CommandButton onSend={() => reflexr.send({ type: "skip_run", run_id: run.id })}>
              Skip
            </CommandButton>
          )}
          {cancel && (
            <CommandButton onSend={() => reflexr.send({ type: "cancel_run", run_id: run.id })}>
              Cancel
            </CommandButton>
          )}
        </>
      ),
    };
  });

  return (
    <>
      {/* The one page that may be recorded: its statuses, counts, times and buttons. What names
          things (a thread's title, a rule, a tracker item) and a comment on a run are blocked in
          their cells, and every other text on it is masked (portalr ADR-0077). */}
      <i hidden data-portalr-replay="allow" />
      <PageHeader
        title="Runs"
        meta={`The agent's turns and the rules' runs in ${workspace}, newest first`}
      />
      <div className="flex flex-col gap-3">
        <SectionTitle>The agent's turns</SectionTitle>
        <Connection snapshot={turns} waiting="the workspace's turns" />
        <RunList
          caption="Turns"
          title="Thread"
          runs={turnParts}
          started
          attempts={false}
          feedback={turnFeedback}
          empty={
            turns.status === "live"
              ? { title: "No turns yet", body: "The agent's turns in a thread are listed here." }
              : undefined
          }
        />
      </div>
      <div className="flex flex-col gap-3">
        <SectionTitle>Rules' runs</SectionTitle>
        <Connection snapshot={automation} waiting="the workspace's rules" />
        <RunList
          caption="Rules' runs"
          title="Rule"
          runs={ruleParts}
          attempts
          feedback={runFeedback}
          empty={
            automation.status === "live"
              ? { title: "No rule runs yet", body: "A rule's runs are listed here as it fires." }
              : undefined
          }
        />
      </div>
    </>
  );
}
