import type { GrantrApi } from "@portalr/client";
import { expect, test } from "vitest";
import { render } from "vitest-browser-react";
import { ApprovalDetails, ApprovalStanding } from "./approval";

type Approval = GrantrApi.components["schemas"]["ApprovalView"];

const PENDING: Approval = {
  id: "apr_1",
  scope: { tenant_id: "acme", workspace_id: "notes" },
  capability: "notes.publish",
  version: "1.2.0",
  rendering: {
    title: "Publish the note",
    summary: "It posts the note to the team's page.",
    arguments: { note: "Weekly‮ update" },
  },
  arguments_digest: "a".repeat(64),
  asked_by: { kind: "person", id: "bob" },
  answerers: { subjects: ["alice"], groups: [], confirmation: false, different_approver: false },
  deadline: "2026-11-02T09:00:00Z",
  asked_at: "2026-11-01T09:00:00Z",
  covers: [],
  scopes_offered: [],
  state: "pending",
};

test("a waiting approval says what it would be called with, by whom, where, and until when", async () => {
  const screen = await render(<ApprovalDetails approval={PENDING} askedBy="bob@acme.test" />);
  await expect.element(screen.getByText("It posts the note to the team's page.")).toBeVisible();
  const called = screen.getByRole("region", { name: "What it would be called with" });
  // A character a reader wouldn't see is shown as its code point, so what is read is what runs.
  await expect.element(called).toBeVisible();
  expect(called.element().textContent).toContain('"note": "Weekly⟦U+202E⟧ update"');
  await expect.element(screen.getByText("bob@acme.test")).toBeVisible();
  await expect.element(screen.getByText("notes.publish")).toBeVisible();
  await expect.element(screen.getByText("notes", { exact: true })).toBeVisible();
  await expect.element(screen.getByText("Expires")).toBeVisible();
  await expect.element(screen.getByText("Approved by")).not.toBeInTheDocument();
});

test("a change is shown as its diff, and a plan's approval names the steps it allows", async () => {
  const plan: Approval = {
    ...PENDING,
    rendering: { title: "Edit the plan", summary: "", diff: "-old\n+new\n" },
    covers: [
      {
        step: "s1",
        capability: "artifactr.edit_text",
        major: 1,
        tier: "write",
        digest: "b".repeat(64),
        max_calls: 3,
      },
      { step: "s2", capability: "artifactr.read_artifact", major: 1, tier: "read", digest: "c" },
    ],
  };
  const screen = await render(<ApprovalDetails approval={plan} askedBy="you" />);
  const change = screen.getByRole("region", { name: "The change it would make" });
  await expect.element(change).toBeVisible();
  expect(change.element().textContent).toContain("-old\n+new");
  await expect
    .element(screen.getByRole("region", { name: "What it would be called with" }))
    .not.toBeInTheDocument();
  const steps = screen.getByRole("region", { name: "The plan's steps it allows" });
  await expect.element(steps).toBeVisible();
  expect(steps.element().textContent).toContain("artifactr.edit_text at step s1, at most 3 times");
  expect(steps.element().textContent).toContain("artifactr.read_artifact at step s2");
});

test("an answered approval says who answered, on which page, and why", async () => {
  const answered: Approval = {
    ...PENDING,
    state: "denied",
    answer: {
      approved: false,
      arguments_digest: "a".repeat(64),
      at: "2026-11-01T10:00:00Z",
      by: { id: "alice", groups: [], service: false },
      surface: "portalr:confirm",
      reason: "Not this week.",
    },
  };
  const screen = await render(
    <ApprovalDetails approval={answered} askedBy="bob" answeredBy="you" />,
  );
  await expect.element(screen.getByText("Denied by")).toBeVisible();
  await expect.element(screen.getByText(/^you, .*, on the confirm page$/u)).toBeVisible();
  await expect.element(screen.getByText("Not this week.")).toBeVisible();
  await expect.element(screen.getByText("Expires")).not.toBeInTheDocument();
  // With no name for who answered, it is their id.
  const approved: Approval = {
    ...answered,
    state: "approved",
    answer: { ...answered.answer!, approved: true, surface: "portalr", reason: null },
  };
  screen.rerender(<ApprovalDetails approval={approved} askedBy="bob" />);
  await expect.element(screen.getByText("Approved by")).toBeVisible();
  await expect.element(screen.getByText(/^alice, /u)).toBeVisible();
  await expect.element(screen.getByText("Why")).not.toBeInTheDocument();
});

test("one that expired or was withdrawn says why", async () => {
  const expired: Approval = { ...PENDING, state: "expired", reason: "No one answered in time." };
  const screen = await render(<ApprovalDetails approval={expired} askedBy="bob" />);
  await expect.element(screen.getByText("No one answered in time.")).toBeVisible();
});

test("where an approval stands is a word on its badge", async () => {
  const screen = await render(
    <>
      <ApprovalStanding state="pending" />
      <ApprovalStanding state="approved" />
      <ApprovalStanding state="denied" />
      <ApprovalStanding state="expired" />
      <ApprovalStanding state="withdrawn" />
    </>,
  );
  for (const word of ["Waiting", "Approved", "Denied", "Expired", "Withdrawn"]) {
    await expect.element(screen.getByText(word)).toBeVisible();
  }
});
