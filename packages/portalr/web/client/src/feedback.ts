/** Feedback as the stores keep it, either library's, and the reader's thumbs read from it. */

/** Feedback someone gave: its type, such as `thumbs`, and its value. */
export interface Feedback<Actor extends object = object> {
  readonly actor: Actor;
  readonly type: string;
  readonly value: Readonly<Record<string, unknown>>;
}

/** A person's thumbs: up or down, and why, if they said. */
export interface Thumb {
  readonly up: boolean;
  readonly comment: string | null;
}

/**
 * A person's latest thumbs among some feedback, or null if they gave none: `me` is the id the
 * server attributes their feedback to.
 */
export function thumbs(given: readonly Feedback[], me: string): Thumb | null {
  const mine = given.filter(
    (feedback) => feedback.type === "thumbs" && "id" in feedback.actor && feedback.actor.id === me,
  );
  const { up, comment } = mine.at(-1)?.value ?? {};
  if (typeof up !== "boolean") {
    return null;
  }
  return { up, comment: typeof comment === "string" && comment ? comment : null };
}
