import { type Reflexr, thumbs } from "@portalr/client";
import { CommandButton, RunStatus, StatusBadge, TextLink, Thumbs, type Tone } from "@portalr/ui";
import { useSuspenseQuery } from "@tanstack/react-query";
import { createFileRoute, Link } from "@tanstack/react-router";
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
    Promise.all([
      context.queryClient.ensureQueryData(
        allowedIn(context.queries, params.tenant, workspaceOf(params.workspace), ACTIONS),
      ),
      context.queryClient.ensureQueryData(context.queries.grantr.memberships(context.user)),
    ]),
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

  return (
    <section aria-labelledby="runs" className="flex flex-col gap-6">
      <h2 id="runs" className="font-semibold text-lg">
        Runs
      </h2>
      <section aria-labelledby="turns" className="flex flex-col gap-2">
        <h3 id="turns" className="font-semibold">
          The agent's turns
        </h3>
        <Connection snapshot={turns} waiting="the workspace's turns" />
        <ul aria-label="Turns" className="flex flex-col gap-3">
          {turnRuns.map((run) => (
            <li key={run.id} aria-label={`Turn ${run.id}`} className="flex flex-col gap-1">
              <span className="flex flex-wrap gap-2 text-sm">
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
                <RunStatus status={run.status} />
              </span>
              {run.status === "running" && allowed.has("artifactr:stop_run") && (
                <CommandButton onSend={() => artifactr.send({ type: "stop_run", run_id: run.id })}>
                  Stop
                </CommandButton>
              )}
              {allowed.has("artifactr:give_feedback") && (
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
              )}
            </li>
          ))}
        </ul>
      </section>
      <section aria-labelledby="rule-runs" className="flex flex-col gap-2">
        <h3 id="rule-runs" className="font-semibold">
          Rules' runs
        </h3>
        <Connection snapshot={automation} waiting="the workspace's rules" />
        <ul aria-label="Rules' runs" className="flex flex-col gap-3">
          {ruleRuns.map((run) => (
            <li key={run.id} aria-label={`Run ${run.id}`} className="flex flex-col gap-1">
              <span className="flex flex-wrap gap-2 text-sm">
                <code className="font-mono">{run.rule}</code>
                <StatusBadge tone={RULE_RUN[run.status][0]} live>
                  {RULE_RUN[run.status][1]}
                </StatusBadge>
                <span className="text-muted">attempt {run.attempt}</span>
                {run.retries > 0 && (
                  <span className="text-muted">
                    retried {run.retries === 1 ? "once" : `${run.retries} times`}
                  </span>
                )}
              </span>
              <span className="flex flex-wrap gap-2">
                {run.status === "dead_lettered" && allowed.has("reflexr:retry_run") && (
                  <CommandButton onSend={() => reflexr.send({ type: "retry_run", run_id: run.id })}>
                    Retry
                  </CommandButton>
                )}
                {(run.status === "dead_lettered" || run.status === "retrying") &&
                  allowed.has("reflexr:skip_run") && (
                    <CommandButton
                      onSend={() => reflexr.send({ type: "skip_run", run_id: run.id })}
                    >
                      Skip
                    </CommandButton>
                  )}
                {(run.status === "pending" ||
                  run.status === "running" ||
                  run.status === "retrying") &&
                  allowed.has("reflexr:cancel_run") && (
                    <CommandButton
                      onSend={() => reflexr.send({ type: "cancel_run", run_id: run.id })}
                    >
                      Cancel
                    </CommandButton>
                  )}
              </span>
              {allowed.has("reflexr:give_feedback") && (
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
              )}
            </li>
          ))}
        </ul>
      </section>
    </section>
  );
}
