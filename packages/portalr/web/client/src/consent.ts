/**
 * A person's answer to product analytics (lattice RFC-0008): read and recorded at portalr's relay,
 * which keeps it in the application's database. No, until the person says yes.
 */

import type { Api } from "./rest";

/** Whether the person has said yes; no, until they do, and no where the relay can't be read. */
export async function readConsent(api: Api): Promise<boolean> {
  const { data } = await api.portalr.GET("/portalr/v1/analytics/consent");
  return data?.given ?? false;
}

/** What became of an answer: recorded, and on a no, whether the deletion is done yet. */
export interface Answered {
  readonly given: boolean;
  /** On a no that owed one: whether the person's events are deleted yet; else none. */
  readonly deleted: boolean | null;
}

/** Record the person's answer; a yes taken back deletes their events. What became of it, or null. */
export async function answerConsent(api: Api, given: boolean): Promise<Answered | null> {
  const { data } = await api.portalr.PUT("/portalr/v1/analytics/consent", { body: { given } });
  return data === undefined ? null : { given: data.given, deleted: data.deleted ?? null };
}
