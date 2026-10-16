/**
 * A workspace's runs: a table from the small breakpoint, named by its caption, and below it a
 * card for each, its status and title on top, then its attempts and feedback, and its actions in
 * reach. What a run's cells hold is its caller's, as the app's and admin's runs differ.
 */

import type { Reflexr } from "@portalr/client";
import type { ReactNode } from "react";
import { StatusBadge, type Tone } from "./status-badge";
import { Table } from "./table";

/** A rule run's status, as the badge shows it: a tone and a word. */
const RULE_RUN: Record<Reflexr.Run["status"], readonly [Tone, string]> = {
  pending: ["queued", "Queued"],
  running: ["working", "Running"],
  retrying: ["queued", "Retrying"],
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

/** A run's parts, as the table's cells and a phone's card both show them. */
export interface RunParts {
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
export function RunList({
  caption,
  title,
  runs,
  attempts,
  feedback,
}: {
  caption: string;
  title: string;
  runs: readonly RunParts[];
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
