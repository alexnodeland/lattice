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

/** Record the person's answer; a yes taken back deletes their events. Whether it was recorded. */
export async function answerConsent(api: Api, given: boolean): Promise<boolean> {
  const { data } = await api.portalr.PUT("/portalr/v1/analytics/consent", { body: { given } });
  return data?.given === given;
}
