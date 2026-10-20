/**
 * The reader's messages on their way: shown in the thread as soon as they are sent, under an id
 * the app chooses, until the thread has them; a message the server refused, or that never left,
 * is taken away again, and the composer says why.
 */

import type { Artifactr, ArtifactrV1 } from "@portalr/client";
import type { Sent } from "@portalr/ui";
import { useState } from "react";

/** A message the reader sent, by the id it was sent with, as the thread will have it. */
export interface Posting {
  readonly id: string;
  readonly content: string;
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
  async function post(content: string, send: (messageId: ArtifactrV1.MessageId) => Sent): Sent {
    const id = messageId();
    setPosting((all) => [...all, { id, content }]);
    const sent = await send(id);
    if (sent.outcome !== "done") {
      setPosting((all) => all.filter((each) => each.id !== id));
    }
    return sent;
  }
  return { posting: posting.filter(({ id }) => !posted.has(id)), post };
}
