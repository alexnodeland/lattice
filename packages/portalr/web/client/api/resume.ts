/** What both integration tests share: the session, and every `seq` a store applies. */

import type { Snapshot } from "../src/stream";

export const session = { token: "portalr", tenant: "acme" };

/** A workspace of the test's own, so a run never sees another's events. */
export const workspace = () => `portalr-${crypto.randomUUID()}`;

/** The base URL of a surface the `api` task started, from its environment. */
export function surface(name: "ARTIFACTR_URL" | "REFLEXR_URL"): string {
  const url = process.env[name];
  if (!url) {
    throw new Error(`${name} is unset: run this through the client's api task`);
  }
  return url;
}

/** Records every `seq` the store applies, in order. */
export function applied<S>(store: {
  snapshot(): Snapshot<S>;
  subscribe(listener: () => void): () => void;
}): number[] {
  const seqs: number[] = [];
  store.subscribe(() => {
    const { seq } = store.snapshot();
    if (seq !== 0 && seq !== seqs.at(-1)) {
      seqs.push(seq);
    }
  });
  return seqs;
}

/** 1, 2, … n: every event once, in order. */
export const every = (n: number) => Array.from({ length: n }, (_, index) => index + 1);
