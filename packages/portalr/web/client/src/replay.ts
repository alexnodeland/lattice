/**
 * A person's answer to session replay (portalr ADR-0077): read and recorded at portalr's relay,
 * apart from analytics' answer, which it rests on. No, until the person says yes.
 */

import type { Answered, Consent } from "./consent";
import type { Api } from "./rest";

/**
 * The person's answer to replay, as the relay reads it.
 *
 * @throws Error if the relay can't be read, as `readConsent` does.
 */
export async function readReplayConsent(api: Api): Promise<Consent> {
  const { data, response } = await api.portalr.GET("/portalr/v1/analytics/replay/consent");
  if (data === undefined) {
    throw new Error(`the answer couldn't be read (${response.status})`);
  }
  return { given: data.given, deleting: data.deleting };
}

/**
 * Record the person's answer to replay; a yes taken back deletes their recordings. A yes needs
 * analytics' yes first.
 *
 * @throws Error if the relay didn't record it, as `answerConsent` does.
 */
export async function answerReplayConsent(api: Api, given: boolean): Promise<Answered> {
  const { data, response } = await api.portalr.PUT("/portalr/v1/analytics/replay/consent", {
    body: { given },
  });
  if (data === undefined) {
    throw new Error(`the answer wasn't recorded (${response.status})`);
  }
  return { given: data.given, deleted: data.deleted ?? null };
}
