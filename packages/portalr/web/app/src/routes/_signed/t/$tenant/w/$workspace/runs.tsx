import { type Reflexr, thumbs } from "@portalr/client";
import {
  CommandButton,
  PageHeader,
  RunStatus,
  SectionTitle,
  StatusBadge,
  Table,
  TextLink,
  Thumbs,
  type Tone,
} from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { useMemo } from "react";
import { allowedIn, workspaceOf } from "../../../../../../allowed";
import { useMe } from "../../../../../../me";
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
 * cancelled, by its status, a queued one only cancelled.
 */
export const Route = createFileRoute("/_signed/t/$tenant/w/$workspace/runs")({
  head: ({ params }) => ({ meta: [{ title: `Runs · ${params.workspace} · portalr` }] }),
  loader: ({ context, params }) =>
    context.queryClient.ensureQueryData(
      allowedIn(context.queries, params.tenant, workspaceOf(params.workspace), ACTIONS),
    ),
  component: Runs,
});

/** Runs, the newest first. */
const newest = <R extends { started: number }>(runs: Readonly<Record<string, R>>) =>
  Object.values(runs).sort((a, b) => b.started - a.started);

/** A rule run's status, as ui's badge shows it: a tone and a word. */
const RULE_RUN: Record<Reflexr.Run["status"], readonly [Tone, string]> = {
  pending: ["queued", "Queued"],
  running: ["working", "Running"],
  retrying: ["queued", "Retrying"],
  succeeded: ["done", "Succeeded"],
  dead_lettered: ["failed", "Dead-lettered"],
  cancelled: ["stopped", "Cancelled"],
  skipped: ["stopped", "Skipped"],
};

/** A run's parts, as the table's cells and a phone's card both show them. */
interface Parts {
  readonly key: string;
  /** The row's or card's name. */
  readonly name: string;
  readonly status: ReactNode;
  readonly title: ReactNode;
  readonly attempts?: number;
  readonly feedback: ReactNode;
  readonly actions: ReactNode;
}

/**
 * Runs as a table, named by its caption, from the small breakpoint; below it, a card for each, its
 * status and title on top, then its attempts and feedback, and its actions in reach.
 */
function RunList({
  caption,
  title,
  runs,
  attempts,
  feedback,
}: {
  caption: string;
  title: string;
  runs: readonly Parts[];
  attempts: boolean;
  feedback: boolean;
}) {
  return (
    <>
      <div className="max-sm:hidden">
        <Table caption={caption}>
          <thead>
            <tr>
              <th scope="col">Status</th>
              <th scope="col">{title}</th>
              {attempts && <th scope="col">Attempts</th>}
              {feedback && <th scope="col">Feedback</th>}
              <th scope="col">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.key} aria-label={run.name}>
                <td>{run.status}</td>
                <td>{run.title}</td>
                {attempts && <td className="text-muted tabular-nums">{run.attempts}</td>}
                {feedback && <td>{run.feedback}</td>}
                <td>
                  <span className="flex flex-wrap justify-end gap-2">{run.actions}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      </div>
      <ul aria-label={caption} className="flex flex-col gap-3 sm:hidden">
        {runs.map((run) => (
          <li
            key={run.key}
            aria-label={run.name}
            className="flex flex-col gap-3 rounded-lg border border-line bg-surface p-4"
          >
            <span className="flex flex-wrap items-center gap-2">
              {run.status}
              {run.title}
            </span>
            {(attempts || feedback) && (
              <span className="flex flex-wrap items-center gap-3 text-sm">
                {attempts && <span className="text-muted">Attempt {run.attempts}</span>}
                {feedback && run.feedback}
              </span>
            )}
            {run.actions && <span className="flex flex-wrap gap-2">{run.actions}</span>}
          </li>
        ))}
      </ul>
    </>
  );
}

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
  const turnFeedback = allowed.has("artifactr:give_feedback");
  const runFeedback = allowed.has("reflexr:give_feedback");

  const turnParts: Parts[] = turnRuns.map((run) => ({
    key: run.id,
    name: `Turn ${run.id}`,
    status: <RunStatus status={run.status} />,
    title: (
      <TextLink
        render={
          <Link
            to="/t/$tenant/w/$workspace/threads/$thread"
            params={{ tenant, workspace, thread: run.threadId }}
          />
        }
      >
        {turns.state.threads[run.threadId]?.title || "Untitled"}
      </TextLink>
    ),
    feedback: turnFeedback && (
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
    ),
    actions: run.status === "running" && allowed.has("artifactr:stop_run") && (
      <CommandButton onSend={() => artifactr.send({ type: "stop_run", run_id: run.id })}>
        Stop
      </CommandButton>
    ),
  }));

  const ruleParts: Parts[] = ruleRuns.map((run) => {
    const [tone, words] = RULE_RUN[run.status];
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
      status: (
        <StatusBadge tone={tone} live>
          {words}
        </StatusBadge>
      ),
      title: (
        <span className="flex flex-col">
          <code className="font-mono">{run.rule}</code>
          {run.retries > 0 && (
            <span className="text-muted text-xs">
              retried {run.retries === 1 ? "once" : `${run.retries} times`}
            </span>
          )}
        </span>
      ),
      attempts: run.attempt,
      feedback: runFeedback && (
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
          attempts={false}
          feedback={turnFeedback}
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
        />
      </div>
    </>
  );
}
