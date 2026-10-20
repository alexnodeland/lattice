/**
 * The reader's messages on their way: shown in the thread as soon as they are sent, under an id
 * the app chooses, until the thread has them. One the server refused is taken away, and the
 * composer gives its words back. One whose answer never came, which the server may have, stays,
 * unsent, to be sent again under the same id, which the server takes once.
 */

import type { Artifactr, ArtifactrV1 } from "@portalr/client";
import type { Sent } from "@portalr/ui";
import { useState } from "react";

/** A message the reader sent, by the id it was sent with, as the thread will have it. */
export interface Posting {
  readonly id: string;
  readonly content: string;
  /** Whether its answer never came: it may have been posted, or not. */
  readonly unsent: boolean;
}

/** A new message's id, as artifactr's own are made. */
const messageId = () => `msg_${crypto.randomUUID().replaceAll("-", "")}`;

/**
 * The messages being posted to a thread that it doesn't have yet, and `post`, which shows one
 * while `send` posts it under the id it is given.
 */
export function usePosting(messages: readonly Artifactr.Message[] | undefined) {
  const [posting, setPosting] = useState<readonly Posting[]>([]);
  const posted = new Set(messages?.map(({ id }) => id));
  const settle = (id: string, change: Partial<Posting> | null) =>
    setPosting((all) =>
      change === null
        ? all.filter((each) => each.id !== id)
        : all.map((each) => (each.id === id ? { ...each, ...change } : each)),
    );
  async function post(
    content: string,
    send: (messageId: ArtifactrV1.MessageId) => Sent,
    id: ArtifactrV1.MessageId = messageId(),
  ): Sent {
    setPosting((all) => [...all.filter((each) => each.id !== id), { id, content, unsent: false }]);
    const sent = await send(id);
    if (sent.outcome === "refused") {
      settle(id, null);
    } else if (sent.outcome === "closed") {
      settle(id, { unsent: true });
    }
    return sent;
  }
  return { posting: posting.filter(({ id }) => !posted.has(id)), post };
}
