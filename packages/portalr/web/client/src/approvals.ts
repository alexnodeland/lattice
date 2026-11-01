/**
 * Approvals as grantr shows them (grantr ADR-0040): who asked, in words, where each is answered,
 * and the tenant's approvals read again once one is answered.
 */

import type { QueryClient } from "@tanstack/react-query";
import type { components as Grantr } from "./generated/grantr.openapi";
import { type Names, shortId } from "./people";
import { keys } from "./queries";

/** An approval as it stands: lattice-core's `Approval`, as grantr's API names it. */
export type Approval = Grantr["schemas"]["ApprovalView"];

/**
 * Admin's confirm page for an approval, where the caller confirms their own `admin_high` call
 * (lattice RFC-0014): the only page that answers a confirmation.
 */
export const confirmPage = (id: string) => `/portalr/admin/confirm/${encodeURIComponent(id)}`;

/** The app's page for an approval in a tenant, where those who may answer it do. */
export const approvalPage = (tenant: string, id: string) =>
  `/portalr/app/t/${encodeURIComponent(tenant)}/approvals/${encodeURIComponent(id)}`;

/** The person a call was asked for: the person who called, or the one a run or session acts for. */
export function askedFor(approval: Approval): string | null {
  const caller = approval.asked_by;
  return caller.kind === "person" ? caller.id : (caller.on_behalf_of ?? null);
}

/**
 * Who asked, in words, for the middle of a sentence: "you", a person by `names`, or an agent's
 * run or a code session and the person it acts for; then the outside client the call came
 * through, if one did.
 */
export function askedBy(approval: Approval, me: string, names: Names = shortId): string {
  const person = (id: string) => (id === me ? "you" : names(id));
  const caller = approval.asked_by;
  const forWhom =
    caller.kind === "person" || caller.on_behalf_of == null
      ? ""
      : ` for ${person(caller.on_behalf_of)}`;
  const who =
    caller.kind === "person"
      ? person(caller.id)
      : caller.kind === "run"
        ? `the agent ${caller.agent}${forWhom}`
        : `a code session${forWhom}`;
  return approval.via == null ? who : `${who}, through ${approval.via.client_name}`;
}

/**
 * Who answered, in words: "you", a person by `names`, or a service principal by its id, which
 * has no email to look up.
 */
export function answeredBy(
  by: Grantr["schemas"]["ApprovalAnswerer"],
  me: string,
  names: Names = shortId,
): string {
  if (by.id === me) {
    return "you";
  }
  return by.service ? by.id : names(by.id);
}

/**
 * The people an approval names whom the reader may know by their email: whom it was asked for,
 * and who answered it, if a person did; never the reader, who is "you".
 */
export function peopleIn(approval: Approval, me: string): string[] {
  const by = approval.answer?.by;
  const named = [askedFor(approval), by === undefined || by.service ? null : by.id];
  return [...new Set(named.filter((id): id is string => id !== null && id !== me))];
}

/**
 * After an answer, given or refused, the tenant's approvals are read again: a refused one may
 * have been answered first by someone else, which its page then shows.
 */
export async function changedApprovals<A>(
  queryClient: QueryClient,
  tenant: string,
  answer: Promise<A>,
): Promise<A> {
  const answered = await answer;
  await queryClient.invalidateQueries({ queryKey: keys.grantr.approvals(tenant) });
  return answered;
}
