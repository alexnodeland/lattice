import { QueryClient } from "@tanstack/react-query";
import { expect, test } from "vitest";
import {
  type Approval,
  answeredBy,
  approvalPage,
  askedBy,
  askedFor,
  changedApprovals,
  confirmPage,
  peopleIn,
} from "./approvals";
import { keys } from "./queries";

/** An approval asked by `asked_by`, through `via` if given, answered by `by` if given. */
function approval(
  asked_by: Approval["asked_by"],
  via: Approval["via"] = null,
  by?: { id: string; service?: boolean },
): Approval {
  return {
    id: "apr_1",
    scope: { tenant_id: "acme", workspace_id: "notes" },
    capability: "notes.publish",
    version: "1.0.0",
    rendering: { title: "Publish the note", summary: "", arguments: {} },
    arguments_digest: "a".repeat(64),
    asked_by,
    via,
    answerers: {
      subjects: ["alice"],
      groups: [],
      confirmation: false,
      different_approver: false,
    },
    deadline: "2026-11-02T09:00:00Z",
    asked_at: "2026-11-01T09:00:00Z",
    covers: [],
    scopes_offered: [],
    state: by === undefined ? "pending" : "approved",
    answer:
      by === undefined
        ? null
        : {
            approved: true,
            arguments_digest: "a".repeat(64),
            at: "2026-11-01T10:00:00Z",
            by: { id: by.id, groups: [], service: by.service ?? false },
            surface: "portalr",
          },
  };
}

const names = (id: string) => `${id}@acme.test`;

test("who asked is the person who called, or the agent's run or code session and whom it is for", () => {
  expect(askedBy(approval({ kind: "person", id: "alice" }), "alice", names)).toBe("you");
  expect(askedBy(approval({ kind: "person", id: "bob" }), "alice", names)).toBe("bob@acme.test");
  expect(
    askedBy(
      approval({ kind: "run", id: "run_1", agent: "notes", on_behalf_of: "bob" }),
      "alice",
      names,
    ),
  ).toBe("the agent notes for bob@acme.test");
  expect(askedBy(approval({ kind: "run", id: "run_1", agent: "notes" }), "alice", names)).toBe(
    "the agent notes",
  );
  expect(
    askedBy(approval({ kind: "session", id: "ses_1", on_behalf_of: "alice" }), "alice", names),
  ).toBe("a code session for you");
  expect(askedBy(approval({ kind: "session", id: "ses_1" }), "alice")).toBe("a code session");
});

test("a call through an outside client says so", () => {
  const via = { connection_id: "con_1", client_name: "Claude", surface: "mcp" } as const;
  expect(askedBy(approval({ kind: "person", id: "alice" }, via), "alice")).toBe(
    "you, through Claude",
  );
});

test("whom it was asked for is the caller, or the person their run or session acts for", () => {
  expect(askedFor(approval({ kind: "person", id: "bob" }))).toBe("bob");
  expect(askedFor(approval({ kind: "run", id: "r", agent: "a", on_behalf_of: "bob" }))).toBe("bob");
  expect(askedFor(approval({ kind: "session", id: "s" }))).toBeNull();
});

test("who answered is the reader, a person by their email, or a service principal by its id", () => {
  const by = (id: string, service = false) => ({ id, groups: [], service });
  expect(answeredBy(by("alice"), "alice", names)).toBe("you");
  expect(answeredBy(by("bob"), "alice", names)).toBe("bob@acme.test");
  expect(answeredBy(by("ci", true), "alice", names)).toBe("ci");
});

test("the people named are whom it was asked for and who answered, never the reader or a key", () => {
  expect(peopleIn(approval({ kind: "person", id: "bob" }, null, { id: "carol" }), "alice")).toEqual(
    ["bob", "carol"],
  );
  expect(
    peopleIn(approval({ kind: "person", id: "alice" }, null, { id: "alice" }), "alice"),
  ).toEqual([]);
  expect(
    peopleIn(approval({ kind: "session", id: "s" }, null, { id: "ci", service: true }), "alice"),
  ).toEqual([]);
  expect(
    peopleIn(approval({ kind: "run", id: "r", agent: "a", on_behalf_of: "bob" }), "bob"),
  ).toEqual([]);
});

test("an approval's pages are the app's, in its tenant, and admin's confirm page", () => {
  expect(approvalPage("acme", "apr_1")).toBe("/portalr/app/t/acme/approvals/apr_1");
  expect(approvalPage("a b", "apr/1")).toBe("/portalr/app/t/a%20b/approvals/apr%2F1");
  expect(confirmPage("apr_1")).toBe("/portalr/admin/confirm/apr_1");
});

test("an answer makes the tenant's approvals stale, and not another's", async () => {
  const client = new QueryClient();
  client.setQueryData(keys.grantr.approvalList("acme"), []);
  client.setQueryData(keys.grantr.approval("acme", "apr_1"), null);
  client.setQueryData(keys.grantr.approvalList("globex"), []);
  client.setQueryData(keys.grantr.members("acme"), []);
  expect(await changedApprovals(client, "acme", Promise.resolve("done"))).toBe("done");
  expect(client.getQueryState(keys.grantr.approvalList("acme"))?.isInvalidated).toBe(true);
  expect(client.getQueryState(keys.grantr.approval("acme", "apr_1"))?.isInvalidated).toBe(true);
  expect(client.getQueryState(keys.grantr.approvalList("globex"))?.isInvalidated).toBe(false);
  expect(client.getQueryState(keys.grantr.members("acme"))?.isInvalidated).toBe(false);
});
