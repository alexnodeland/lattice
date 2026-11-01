/**
 * The tenant's approvals as routes, over a stubbed grantr (grantr ADR-0040): the list of those
 * waiting for alice, each approval's page, answering on it, and a confirmation, which only
 * admin's confirm page answers.
 */

import type { Approval } from "@portalr/client";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { page } from "vitest/browser";
import { open, type Serve } from "./test/app";

const APPROVALS = "/grantr/v1/tenants/acme/approvals";

/** An approval in acme's notes, waiting, asked by bob's run, which alice may answer. */
function approval(id: string, change: Partial<Approval> = {}): Approval {
  return {
    id,
    scope: { tenant_id: "acme", workspace_id: "notes" },
    capability: "notes.publish",
    version: "1.0.0",
    rendering: { title: `Publish ${id}`, summary: "", arguments: { note: id } },
    arguments_digest: "a".repeat(64),
    asked_by: { kind: "run", id: "run_1", agent: "notes", on_behalf_of: "bob" },
    answerers: { subjects: ["alice"], groups: [], confirmation: false, different_approver: false },
    deadline: "2099-01-01T00:00:00Z",
    asked_at: "2026-11-01T09:00:00Z",
    covers: [],
    scopes_offered: [],
    state: "pending",
    ...change,
  };
}

/**
 * grantr's approvals, as `approvals` holds them, and whether alice may answer each: those she
 * may are listed. An answer settles one, unless `refuse` says how grantr refuses it.
 */
function grantr(
  approvals: Map<string, Approval>,
  answerable: (approval: Approval) => boolean = () => true,
  refuse?: { status: number; type: string; message: string },
): { serve: Serve; answers: unknown[] } {
  const answers: unknown[] = [];
  const serve: Serve = async (request, path) => {
    if (path === APPROVALS) {
      return Response.json([...approvals.values()].filter(answerable));
    }
    const id = path.slice(APPROVALS.length + 1).split("/")[0] ?? "";
    const shown = approvals.get(id);
    if (!path.startsWith(`${APPROVALS}/`) || shown === undefined) {
      return Response.json({ detail: { type: "not_found", message: "no" } }, { status: 404 });
    }
    if (request.method === "GET") {
      return Response.json(shown);
    }
    const given = (await request.json()) as { approved: boolean; reason: string | null };
    answers.push(given);
    if (refuse !== undefined) {
      const { status, ...detail } = refuse;
      approvals.set(id, { ...shown, state: "denied" });
      return Response.json({ detail }, { status });
    }
    const settled: Approval = {
      ...shown,
      state: given.approved ? "approved" : "denied",
      answer: {
        approved: given.approved,
        arguments_digest: shown.arguments_digest,
        at: "2026-11-01T10:00:00Z",
        by: { id: "alice", groups: [], service: false },
        surface: "portalr",
        reason: given.reason,
      },
    };
    approvals.set(id, settled);
    return Response.json(settled);
  };
  return { serve, answers };
}

beforeEach(async () => {
  await page.viewport(1280, 900);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

test("the list has what waits for alice, each opening its page, and her confirmation admin's", async () => {
  const approvals = new Map([
    ["apr_1", approval("apr_1")],
    [
      "apr_2",
      approval("apr_2", {
        asked_by: { kind: "person", id: "alice" },
        via: { connection_id: "con_1", client_name: "Claude", surface: "mcp" },
        answerers: {
          subjects: ["alice"],
          groups: [],
          confirmation: true,
          different_approver: false,
        },
      }),
    ],
  ]);
  const { screen } = await open("/t/acme/approvals", grantr(approvals).serve);
  const rows = screen.getByRole("list", { name: "Approvals waiting for you" });
  await expect
    .element(rows.getByRole("link", { name: "Publish apr_1" }))
    .toHaveAttribute("href", "/t/acme/approvals/apr_1");
  await expect
    .element(rows.getByText(/^Asked by the agent notes for bob in notes, /u))
    .toBeVisible();
  await expect
    .element(rows.getByRole("link", { name: "Publish apr_2" }))
    .toHaveAttribute("href", "/portalr/admin/confirm/apr_2");
  await expect
    .element(
      rows.getByText(/^Asked by you, through Claude in notes, .*Yours to confirm, in admin\.$/u),
    )
    .toBeVisible();
});

test("with nothing waiting, the list says so", async () => {
  const { screen } = await open("/t/acme/approvals", grantr(new Map()).serve);
  await expect.element(screen.getByText("Nothing waits for you")).toBeVisible();
});

test("alice approves on its page, with her reason, and the page shows it settled", async () => {
  const { serve, answers } = grantr(new Map([["apr_1", approval("apr_1")]]));
  const { screen } = await open("/t/acme/approvals/apr_1", serve);
  await expect
    .element(screen.getByRole("heading", { name: "Publish apr_1", level: 1 }))
    .toBeVisible();
  await expect.element(screen.getByText("Waiting", { exact: true })).toBeVisible();
  await screen.getByRole("textbox", { name: "Why" }).fill("  Ship it.  ");
  await screen.getByRole("button", { name: "Approve" }).click();
  await expect.element(screen.getByText("Approved", { exact: true })).toBeVisible();
  expect(answers).toEqual([
    {
      approved: true,
      arguments_digest: "a".repeat(64),
      reason: "Ship it.",
      surface: "portalr",
    },
  ]);
  await expect.element(screen.getByText("Approved by")).toBeVisible();
  await expect.element(screen.getByText("Ship it.", { exact: true })).toBeVisible();
  await expect.element(screen.getByRole("button", { name: "Approve" })).not.toBeInTheDocument();
});

test("a denial refused, as one answered first, says why, and the page shows the first answer", async () => {
  const { serve } = grantr(new Map([["apr_1", approval("apr_1")]]), () => true, {
    status: 409,
    type: "invalid_state",
    message: "approval apr_1 is denied",
  });
  const { screen } = await open("/t/acme/approvals/apr_1", serve);
  await screen.getByRole("button", { name: "Deny" }).click();
  await expect
    .element(screen.getByRole("alert"))
    .toHaveTextContent("It wasn't denied: that can't be done as things stand.");
  await expect.element(screen.getByText("Denied", { exact: true })).toBeVisible();
});

test("the person it was asked for sees where it stands, with nothing to answer", async () => {
  const { screen } = await open(
    "/t/acme/approvals/apr_1",
    grantr(new Map([["apr_1", approval("apr_1")]]), () => false).serve,
  );
  await expect
    .element(screen.getByText("It waits for one of those who may answer it."))
    .toBeVisible();
  await expect.element(screen.getByRole("button", { name: "Approve" })).not.toBeInTheDocument();
});

test("a confirmation is answered on admin's confirm page alone: its caller is sent there", async () => {
  const confirmation = approval("apr_2", {
    asked_by: { kind: "person", id: "alice" },
    answerers: { subjects: ["alice"], groups: [], confirmation: true, different_approver: false },
  });
  const { screen } = await open(
    "/t/acme/approvals/apr_2",
    grantr(new Map([["apr_2", confirmation]])).serve,
  );
  await expect
    .element(screen.getByRole("link", { name: "Open the confirm page" }))
    .toHaveAttribute("href", "/portalr/admin/confirm/apr_2");
  await expect.element(screen.getByRole("button", { name: "Approve" })).not.toBeInTheDocument();
});

test("anyone else sees a confirmation wait for its caller", async () => {
  const confirmation = approval("apr_2", {
    asked_by: { kind: "person", id: "bob" },
    answerers: { subjects: ["bob"], groups: [], confirmation: true, different_approver: false },
  });
  const { screen } = await open(
    "/t/acme/approvals/apr_2",
    grantr(new Map([["apr_2", confirmation]]), () => false).serve,
  );
  await expect
    .element(screen.getByText("It waits for the person who called to confirm it."))
    .toBeVisible();
});

test("an approval alice may not see isn't there, with the way back to the list", async () => {
  const { screen } = await open("/t/acme/approvals/apr_9", grantr(new Map()).serve);
  await expect.element(screen.getByRole("heading", { name: "Approval not found" })).toBeVisible();
  await expect
    .element(screen.getByRole("link", { name: "All approvals" }))
    .toHaveAttribute("href", "/t/acme/approvals");
});
