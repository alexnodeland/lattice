/**
 * Who posted a message, as the thread names them (portalr ADR-0038): the reader as "You", a person
 * by the name they posted under, else by their email where the server names them, else by a short
 * id. The emails are looked up when a message is drawn and kept nowhere else: the stream's state
 * holds the actors as the server sent them.
 */

import { type ArtifactrV1, type Names, shortId } from "@portalr/client";

/**
 * How to name who posted a message: the reader as "You", a person by the name they posted under,
 * else by `names`, an agent as the assistant, and an external agent, the system or an evaluator
 * each as themselves.
 */
export function author(actor: ArtifactrV1.Actor, me: string, names: Names = shortId): string {
  switch (actor.kind) {
    case "user":
      return actor.id === me ? "You" : (actor.name ?? names(actor.id));
    case "agent":
      return "Assistant";
    case "external_agent":
      return actor.name ?? actor.client_id;
    case "system":
      return actor.name ?? "System";
    case "evaluator":
      return actor.name;
    default:
      return actor satisfies never;
  }
}

/** The ids of the people in some messages whom `author` would name by their email: not the reader,
 * and not anyone who posted under a name. */
export const unnamedPeople = (
  messages: readonly { readonly actor: ArtifactrV1.Actor }[],
  me: string,
): string[] =>
  messages.flatMap(({ actor }) =>
    actor.kind === "user" && actor.name == null && actor.id !== me ? [actor.id] : [],
  );
