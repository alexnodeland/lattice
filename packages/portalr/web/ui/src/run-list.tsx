/**
 * A workspace's runs: a table from the small breakpoint, named by its caption, and below it a
 * list of rows (portalr ADR-0060), each its title, then its attempts and feedback, and at its end
 * its status and its actions. What a run's cells hold is its caller's, as the app's and admin's
 * runs differ.
 */

import type { Reflexr } from "@portalr/client";
import type { ReactNode } from "react";
import { EmptyState } from "./empty-state";
import { Num } from "./num";
import { Row, Rows } from "./rows";
import { StatusBadge, type Tone } from "./status-badge";
import { Table } from "./table";

/** A rule run's status, as the badge shows it: a tone and a word. */
const RULE_RUN: Record<Reflexr.Run["status"], readonly [Tone, string]> = {
  pending: ["queued", "Queued"],
  running: ["working", "Running"],
  retrying: ["retrying", "Retrying"],
  succeeded: ["done", "Succeeded"],
  dead_lettered: ["failed", "Dead-lettered"],
  cancelled: ["stopped", "Cancelled"],
  skipped: ["stopped", "Skipped"],
};

/** A rule run's status, in words and a shape, updating as the run does. */
export function RuleRunStatus({ status }: { status: Reflexr.Run["status"] }) {
  const [tone, words] = RULE_RUN[status];
  return (
    <StatusBadge tone={tone} live>
      {words}
    </StatusBadge>
  );
}

/** A run's parts, as the table's cells and a phone's row both show them. */
export interface RunParts {
  readonly key: string;
  /** The row's name, for assistive technology. */
  readonly name: string;
  readonly status: ReactNode;
  readonly title: ReactNode;
  /** When it started, where the list says. */
  readonly started?: ReactNode;
  readonly attempts?: number;
  readonly feedback: ReactNode;
  readonly actions: ReactNode;
}

/**
 * Runs as a table, named by its caption, from the small breakpoint; below it, a row for each, its
 * title, then when it started, its attempts and feedback, and at its end its status and its
 * actions. With none, what `empty` says, where it is given, rather than a table with no rows.
 */
export function RunList({
  caption,
  title,
  runs,
  started = false,
  attempts,
  feedback,
  empty,
}: {
  caption: string;
  title: string;
  runs: readonly RunParts[];
  /** Whether a run's start is a column of its own. */
  started?: boolean;
  attempts: boolean;
  feedback: boolean;
  /** What the list says while it has no runs: its title and a line. */
  empty?: { readonly title: string; readonly body: string } | undefined;
}) {
  if (runs.length === 0 && empty) {
    return <EmptyState title={empty.title}>{empty.body}</EmptyState>;
  }
  return (
    <>
      <div className="max-sm:hidden">
        <Table caption={caption}>
          <thead>
            <tr>
              <th scope="col">Status</th>
              <th scope="col">{title}</th>
              {started && <th scope="col">Started</th>}
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
                {started && <td className="text-muted">{run.started}</td>}
                {attempts && (
                  <td className="text-muted">
                    <Num>{String(run.attempts ?? "")}</Num>
                  </td>
                )}
                {feedback && <td>{run.feedback}</td>}
                <td>
                  <span className="flex flex-wrap justify-end gap-2">{run.actions}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </Table>
      </div>
      <div className="sm:hidden">
        <Rows label={caption}>
          {runs.map((run) => (
            <Row
              key={run.key}
              aria-label={run.name}
              name={run.title}
              meta={
                (started || attempts || feedback) && (
                  <span className="flex flex-wrap items-center gap-3">
                    {started && run.started}
                    {attempts && <span>Attempt {run.attempts}</span>}
                    {feedback && run.feedback}
                  </span>
                )
              }
              end={
                <>
                  {run.status}
                  {run.actions}
                </>
              }
            />
          ))}
        </Rows>
      </div>
    </>
  );
}
