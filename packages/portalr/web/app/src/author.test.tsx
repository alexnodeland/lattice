import { type Artifactr, type ArtifactrV1, namesOf } from "@portalr/client";
import { Message, Messages } from "@portalr/ui";
import { expect, test } from "vitest";
import { render } from "vitest-browser-react";
import { author, unnamedPeople } from "./author";

const ADA = "3f2a91c4-1111-4222-8333-444455556666";
const GONE = "c0ffee00-1111-4222-8333-444455556666";
const ME = "7e1d44aa-1111-4222-8333-444455556666";

const names = namesOf({ [ADA]: "ada@acme.test" });

test("a message is by its author: a person by email, a short id, or the name they posted under", () => {
  expect(author({ kind: "user", id: ME }, ME, names)).toBe("You");
  expect(author({ kind: "user", id: ADA }, ME, names)).toBe("ada@acme.test");
  expect(author({ kind: "user", id: GONE }, ME, names)).toBe("c0ffee00…");
  expect(author({ kind: "user", id: GONE, name: "Gail" }, ME, names)).toBe("Gail");
  expect(author({ kind: "user", id: "alice" }, ME)).toBe("alice");
});

test("an agent, a client, the system and an evaluator are each themselves", () => {
  expect(author({ kind: "agent", thread_id: "thr_1" }, ME, names)).toBe("Assistant");
  expect(author({ kind: "external_agent", client_id: "ci" }, ME, names)).toBe("ci");
  expect(author({ kind: "external_agent", client_id: "ci", name: "Build" }, ME, names)).toBe(
    "Build",
  );
  expect(author({ kind: "system" }, ME, names)).toBe("System");
  expect(author({ kind: "evaluator", name: "judge", version: "1" }, ME, names)).toBe("judge");
});

test("only people without a name of their own, other than the reader, are looked up", () => {
  const actors: ArtifactrV1.Actor[] = [
    { kind: "user", id: ADA },
    { kind: "user", id: ME },
    { kind: "user", id: GONE, name: "Gail" },
    { kind: "user", id: GONE, name: null },
    { kind: "agent", thread_id: "thr_1" },
    { kind: "system" },
  ];
  expect(
    unnamedPeople(
      actors.map((actor) => ({ actor })),
      ME,
    ),
  ).toEqual([ADA, GONE]);
});

test("a thread draws resolved and unresolved authors side by side, and the actors stay as sent", async () => {
  const actors: ArtifactrV1.Actor[] = [
    { kind: "user", id: ADA },
    { kind: "user", id: GONE },
    { kind: "user", id: ME },
    { kind: "agent", thread_id: "thr_1" },
  ];
  const messages: Artifactr.Message[] = actors.map((actor, index) => ({
    id: `m${index}`,
    seq: index + 1,
    actor,
    content: `message ${index}`,
    kind: "message",
    runId: null,
    feedback: [],
  }));
  const screen = await render(
    <Messages>
      {messages.map((message) => (
        <Message key={message.id} message={message} author={author(message.actor, ME, names)} />
      ))}
    </Messages>,
  );
  for (const label of ["ada@acme.test", "c0ffee00…", "You", "Assistant"]) {
    await expect.element(screen.getByText(label, { exact: true })).toBeVisible();
  }
  expect(JSON.stringify(messages)).not.toContain("@acme.test");
});
