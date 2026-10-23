/**
 * A person's answer to product analytics (lattice RFC-0008): read and recorded at portalr's relay,
 * which keeps it in the application's database. No, until the person says yes.
 */

import type { Api } from "./rest";

/** A person's answer, as read: and whether a deletion their no asked for is still to be done. */
export interface Consent {
  readonly given: boolean;
  readonly deleting: boolean;
}

/** Before the answer is first read: not sharing, and nothing known to be owed. */
export const NOT_READ: Consent = { given: false, deleting: false };

/**
 * The person's answer, as the relay reads it.
 *
 * @throws Error if the relay can't be read: a screen keeps the last answer it read, or
 *   `NOT_READ` before the first, rather than taking a failure for a no.
 */
export async function readConsent(api: Api): Promise<Consent> {
  const { data, response } = await api.portalr.GET("/portalr/v1/analytics/consent");
  if (data === undefined) {
    throw new Error(`the answer couldn't be read (${response.status})`);
  }
  return { given: data.given, deleting: data.deleting };
}

/** What became of an answer: recorded, and on a no, whether the deletion is done yet. */
export interface Answered {
  readonly given: boolean;
  /** On a no that owed one: whether the person's events are deleted yet; else none. */
  readonly deleted: boolean | null;
}

/**
 * Record the person's answer; a yes taken back deletes their events.
 *
 * @throws Error if the relay didn't record it: a screen says so, and keeps the answer it had.
 */
export async function answerConsent(api: Api, given: boolean): Promise<Answered> {
  const { data, response } = await api.portalr.PUT("/portalr/v1/analytics/consent", {
    body: { given },
  });
  if (data === undefined) {
    throw new Error(`the answer wasn't recorded (${response.status})`);
  }
  return { given: data.given, deleted: data.deleted ?? null };
}
