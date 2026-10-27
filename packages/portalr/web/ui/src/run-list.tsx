/**
 * A workspace's runs: a table from the small breakpoint, named by its caption, and below it a
 * list of rows (portalr ADR-0060), each its title, then its attempts and feedback, and at its end
 * its status and its actions. What a run's cells hold is its caller's, as the app's and admin's
 * runs differ.
 */

import type { Reflexr, Thumb } from "@portalr/client";
import type { ReactNode } from "react";
import { ActionsMenu, type GiveThumbs, Thumbs } from "./chat";
import { EmptyState } from "./empty-state";
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
  /** The reader's thumbs on it and how to give them, where they may; null where not. */
  readonly feedback: { readonly given: Thumb | null; readonly onThumbs: GiveThumbs } | null;
  readonly actions: ReactNode;
}

/**
 * Runs as a table, named by its caption, from the small breakpoint; below it, a row for each, its
 * status, its title, then when it started and its attempts past the first, and at its end its
 * actions. Thumbs are quiet (portalr ADR-0085): in the table they show as the pointer rests on a
 * row or the keyboard reaches them; in a row, they are in its menu, a sheet on a phone. With
 * none, what `empty` says, where it is given, rather than a table with no rows.
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
              {attempts && (
                <th scope="col" data-num="">
                  Attempts
                </th>
              )}
              {feedback && <th scope="col">Feedback</th>}
              <th scope="col">
                <span className="sr-only">Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.key} aria-label={run.name} className="group">
                <td>{run.status}</td>
                <td>{run.title}</td>
                {started && <td className="text-muted">{run.started}</td>}
                {attempts && (
                  <td className="text-muted" data-num="">
                    {/* The first attempt goes without saying. */}
                    {run.attempts !== 1 && run.attempts}
                  </td>
                )}
                {feedback && (
                  <td>
                    {run.feedback && (
                      <span
                        data-portalr-replay="block"
                        className="block fine:opacity-0 fine:group-focus-within:opacity-100 fine:group-hover:opacity-100"
                      >
                        <Thumbs given={run.feedback.given} onThumbs={run.feedback.onThumbs} />
                      </span>
                    )}
                  </td>
                )}
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
              name={
                <span className="flex flex-col items-start gap-1">
                  {run.status}
                  {run.title}
                </span>
              }
              meta={
                (started || (attempts && run.attempts !== 1)) && (
                  <span className="flex flex-wrap items-center gap-3">
                    {started && run.started}
                    {attempts && run.attempts !== 1 && <span>Attempt {run.attempts}</span>}
                  </span>
                )
              }
              end={
                (run.actions || (feedback && run.feedback)) && (
                  <>
                    {run.actions}
                    {feedback && run.feedback && (
                      <span data-portalr-replay="block">
                        <ActionsMenu
                          label={`Feedback on ${run.name}`}
                          given={run.feedback.given}
                          onThumbs={run.feedback.onThumbs}
                        />
                      </span>
                    )}
                  </>
                )
              }
            />
          ))}
        </Rows>
      </div>
    </>
  );
}
