/**
 * A command a part hands its caller, in flight: whether it is, how it ended, and why one wasn't
 * done, said where it was asked for. The chat's parts and a form's share it.
 */

import { useState } from "react";
import { Alert } from "./alert";
import { isObject } from "./json";

/**
 * How a command a part handed its caller ended, as `client`'s stream settles it: done, refused, or
 * not sent, and, where the server answered, its result, whose rejection says why it was refused.
 */
export type Sent = Promise<{
  readonly outcome: "done" | "refused" | "closed";
  readonly result?: { readonly rejection?: unknown };
}>;

const UNSENT = {
  refused: "That wasn't done: the server refused it.",
  closed: "That wasn't sent: the connection closed.",
  // An integration it needs is off here: said of the workspace, never of the reader's grants.
  not_enabled: "Not available in this workspace.",
  // The application defines no such feedback: said of the workspace, with the type left out.
  no_feedback: "Thumbs aren't available in this workspace.",
} as const;

/** Why a command wasn't done, in words, by how it ended and the server's rejection. */
const unsentSaid = (outcome: "refused" | "closed", rejection: unknown) => {
  if (outcome === "refused" && isObject(rejection)) {
    if (rejection.type === "not_enabled") {
      return UNSENT.not_enabled;
    }
    if (rejection.type === "not_found" && rejection.entity === "feedback type") {
      return UNSENT.no_feedback;
    }
  }
  return UNSENT[outcome];
};

/** How a command ended, as a `Sent` settles. */
type Settled = Awaited<Sent>;

/**
 * A command in flight: whether it is, and why the last one wasn't done. `send` says whether it
 * was; a caller that says why itself, as a form puts a refusal under its fields, gives `told`,
 * which says so of each that wasn't, and is then the only one to say it.
 */
export function useSending() {
  const [pending, setPending] = useState(false);
  const [unsent, setUnsent] = useState<string | null>(null);
  async function send(command: () => Sent, told?: (settled: Settled) => boolean): Promise<boolean> {
    setPending(true);
    setUnsent(null);
    const settled = await command();
    setPending(false);
    if (settled.outcome === "done") {
      return true;
    }
    if (!told?.(settled)) {
      setUnsent(unsentSaid(settled.outcome, settled.result?.rejection));
    }
    return false;
  }
  /** Forget why the last one wasn't done, as a form does once it is changed and checked again. */
  const forget = () => setUnsent(null);
  return { pending, unsent, send, forget };
}

/** Why a command wasn't done, announced. */
export function Unsent({ reason }: { reason: string | null }) {
  return reason && <Alert tone="error">{reason}</Alert>;
}
