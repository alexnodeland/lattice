/**
 * Runs' address and rules (portalr ADR-0032): the workspace whose rule runs are shown, whether
 * those needing attention or every one, what a person may do to a run in each of its states, and
 * how an actor is named.
 */

import type { Reflexr } from "@portalr/client";

type Status = Reflexr.Run["status"];

/** Which runs to list: the ones that need someone, or all. The first is the default. */
export const SHOWN = [
  { show: "attention", label: "Needs attention" },
  { show: "all", label: "Every state" },
] as const;

export type Show = (typeof SHOWN)[number]["show"];

/** What Runs' address keeps: a workspace, and which runs to list. */
export type Shown = {
  /** None until the person chooses one: the first of the tenant's is then shown. */
  readonly workspace?: string | undefined;
  readonly show?: Show;
};

/** A workspace's name as grantr and artifactr take one: any text but NUL, up to 256 characters. */
const nameOf = (value: unknown): string | undefined => {
  const read = typeof value === "string" ? value : "";
  return read !== "" && read.length <= 256 && !read.includes("\0") ? read : undefined;
};

/** The address's workspace and list: a list Runs doesn't offer is its default. */
export function shownOf(search: Record<string, unknown>): Required<Shown> {
  return {
    workspace: nameOf(search.workspace),
    show: SHOWN.find((one) => one.show === search.show)?.show ?? SHOWN[0].show,
  };
}

/**
 * The statuses of the runs that need someone: a run that failed every attempt, and one that is
 * failing and waiting to try again.
 */
const ATTENTION: ReadonlySet<Status> = new Set(["dead_lettered", "retrying"]);

/** Runs to list, the newest first. */
export function listed(runs: Readonly<Record<string, Reflexr.Run>>, show: Show): Reflexr.Run[] {
  return Object.values(runs)
    .filter((run) => show === "all" || ATTENTION.has(run.status))
    .sort((a, b) => b.started - a.started);
}

/** What a person may do to a run: reflexr's commands, and the action grantr checks for each. */
const ACTIONS = ["retry", "skip", "cancel"] as const;
export type Action = (typeof ACTIONS)[number];

/** The action grantr checks for each, in the workspace. */
export const GRANTS = ACTIONS.map((action) => `reflexr:${action}_run` as const);

/** The workspace shown when the address names none: the first of the tenant's, by name. */
export const firstOf = (workspaces: readonly string[]): string | undefined =>
  [...workspaces].sort()[0];

/** How long the stream may be connecting before the page says it can't get through, in ms. */
export const PATIENCE = 10_000;

/**
 * The states each action may be taken in, as reflexr allows them (its run lifecycle): a retry
 * makes a run that failed, was cancelled or skipped, or is waiting to try again, runnable now; a
 * skip gives up on a run that is waiting or failed, which unblocks the runs after it; a cancel
 * stops one that hasn't finished, and discards what a running attempt gives.
 */
const TAKEN_IN: Record<Action, ReadonlySet<Status>> = {
  retry: new Set(["dead_lettered", "retrying", "cancelled", "skipped"]),
  skip: new Set(["pending", "retrying", "dead_lettered"]),
  cancel: new Set(["pending", "running", "retrying", "dead_lettered"]),
};

/** The actions a run's status offers, where grantr allows them. */
export const offered = (status: Status, allowed: ReadonlySet<string>): Action[] =>
  ACTIONS.filter((action) => TAKEN_IN[action].has(status) && allowed.has(`reflexr:${action}_run`));

/** What each intervention is called, in the past tense. */
export const DONE: Record<Reflexr.Intervention["kind"], string> = {
  retried: "made it runnable again",
  skipped: "skipped it",
  cancelled: "cancelled it",
};

/** An actor as people read it: a person's name or id, or what else it is. */
export function actorName(actor: Reflexr.Intervention["actor"]): string {
  const named = "name" in actor && actor.name ? actor.name : null;
  return named ?? ("id" in actor && actor.id ? actor.id : actor.kind);
}

/** What the server said of a command it refused, in words for the person who sent it. */
export function refusedAs(rejection: { readonly [key: string]: unknown } | null | undefined) {
  switch (rejection?.type) {
    case "forbidden":
      return "You aren't allowed to do this to this run.";
    case "not_found":
      return "This run no longer exists.";
    case "invalid_state":
      return "The run has changed, and can't take this now: what it is now is shown above.";
    default:
      return typeof rejection?.message === "string" && rejection.message !== ""
        ? rejection.message
        : "The server refused it.";
  }
}

/** A command for an action on a run: with the reason, if one was given. */
export function commandFor(action: Action, run: string, reason: string) {
  return action === "retry"
    ? ({ type: "retry_run", run_id: run } as const)
    : ({
        type: action === "skip" ? "skip_run" : "cancel_run",
        run_id: run,
        ...(reason === "" ? {} : { reason }),
      } as const);
}
