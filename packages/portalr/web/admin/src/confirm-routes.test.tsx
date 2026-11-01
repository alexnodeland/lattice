/**
 * The confirm page as a route, over a stubbed grantr (lattice RFC-0014, ADR-0038): found in
 * whichever of alice's tenants shows it, read afresh, confirmed only once the tenant's name is
 * typed, on the `portalr:confirm` surface, and refused to anyone but the caller.
 */

import type { Approval } from "@portalr/client";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { page, userEvent } from "vitest/browser";
import { open, type Serve } from "./test/admin";

/** alice's own `admin_high` call in globex, through Claude, waiting for her confirmation. */
function confirmation(change: Partial<Approval> = {}): Approval {
  return {
    id: "apr_1",
    scope: { tenant_id: "globex", workspace_id: "main" },
    capability: "grantr.revoke_key",
    version: "1.0.0",
    rendering: { title: "Revoke a key", summary: "", arguments: { key: "key_ci" } },
    arguments_digest: "a".repeat(64),
    asked_by: { kind: "person", id: "alice" },
    via: { connection_id: "con_1", client_name: "Claude", surface: "mcp" },
    answerers: { subjects: ["alice"], groups: [], confirmation: true, different_approver: false },
    deadline: "2099-01-01T00:00:00Z",
    asked_at: "2026-11-01T09:00:00Z",
    covers: [],
    scopes_offered: [],
    state: "pending",
    ...change,
  };
}

/**
 * grantr, showing `shown` in globex alone, and refusing it in every other tenant as not there;
 * an answer settles it, unless `refuse` says how grantr refuses it.
 */
function grantr(
  shown: Approval,
  refuse?: { status: number; type: string; message: string },
): { serve: Serve; answers: unknown[]; reads: string[] } {
  let current = shown;
  const answers: unknown[] = [];
  const reads: string[] = [];
  const serve: Serve = async (request, path) => {
    // The approvals the store lists for alice: this one, while it waits, where she may answer it.
    if (path === "/grantr/v1/tenants/globex/approvals") {
      const hers = current.state === "pending" && current.answerers.subjects.includes("alice");
      return Response.json(hers ? [current] : []);
    }
    const match = /^\/grantr\/v1\/tenants\/([^/]+)\/approvals\/apr_1(\/answer)?$/u.exec(path);
    if (match === null) {
      return undefined;
    }
    if (match[1] !== "globex") {
      reads.push(match[1] ?? "");
      return Response.json({ detail: { type: "not_found", message: "no" } }, { status: 404 });
    }
    if (request.method === "GET") {
      reads.push("globex");
      return Response.json(current);
    }
    const given = (await request.json()) as { approved: boolean };
    answers.push(given);
    if (refuse !== undefined) {
      const { status, ...detail } = refuse;
      return Response.json({ detail }, { status });
    }
    current = {
      ...current,
      state: given.approved ? "approved" : "denied",
      answer: {
        approved: given.approved,
        arguments_digest: current.arguments_digest,
        at: "2026-11-01T10:00:00Z",
        by: { id: "alice", groups: [], service: false },
        surface: "portalr:confirm",
      },
    };
    return Response.json(current);
  };
  return { serve, answers, reads };
}

beforeEach(async () => {
  await page.viewport(1280, 900);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

test("alice confirms her own call once she types its tenant, on the confirm page's surface", async () => {
  const { serve, answers, reads } = grantr(confirmation());
  const { screen } = await open("/confirm/apr_1", [], serve, ["acme", "globex"]);
  await expect
    .element(screen.getByRole("heading", { name: "Confirm: Revoke a key", level: 1 }))
    .toBeVisible();
  // Asked in each of her tenants, in order, until one shows it.
  expect(reads).toEqual(["acme", "globex"]);
  await expect
    .element(screen.getByText(/In globex, asked by you, through Claude\./u))
    .toBeVisible();
  const confirm = screen.getByRole("button", { name: "Confirm" });
  await expect.element(confirm).toBeDisabled();
  await screen.getByRole("textbox", { name: "Type globex to confirm" }).fill("acme");
  await expect.element(confirm).toBeDisabled();
  await screen.getByRole("textbox", { name: "Type globex to confirm" }).fill("globex");
  await confirm.click();
  await expect.element(screen.getByText("Approved", { exact: true })).toBeVisible();
  expect(answers).toEqual([
    {
      approved: true,
      arguments_digest: "a".repeat(64),
      reason: null,
      surface: "portalr:confirm",
    },
  ]);
  await expect.element(screen.getByText(/, on the confirm page$/u)).toBeVisible();
  await expect.element(screen.getByRole("button", { name: "Confirm" })).not.toBeInTheDocument();
});

test("Enter with the tenant's name typed confirms, and without it does nothing", async () => {
  const { serve, answers } = grantr(confirmation());
  const { screen } = await open("/confirm/apr_1", [], serve, ["globex"]);
  const typed = screen.getByRole("textbox", { name: "Type globex to confirm" });
  await typed.fill("glo");
  await userEvent.keyboard("{Enter}");
  expect(answers).toEqual([]);
  await typed.fill("globex");
  await userEvent.keyboard("{Enter}");
  await expect.element(screen.getByText("Approved", { exact: true })).toBeVisible();
  expect(answers).toHaveLength(1);
});

test("she cancels it without typing anything", async () => {
  const { serve, answers } = grantr(confirmation());
  const { screen } = await open("/confirm/apr_1", [], serve, ["globex"]);
  await screen.getByRole("button", { name: "Cancel it" }).click();
  await expect.element(screen.getByText("Denied", { exact: true })).toBeVisible();
  expect(answers).toMatchObject([{ approved: false, surface: "portalr:confirm" }]);
});

test("a confirmation refused, as past its deadline, says why", async () => {
  const { serve } = grantr(confirmation(), {
    status: 409,
    type: "invalid_state",
    message: "approval apr_1 has expired",
  });
  const { screen } = await open("/confirm/apr_1", [], serve, ["globex"]);
  await screen.getByRole("textbox", { name: "Type globex to confirm" }).fill("globex");
  await screen.getByRole("button", { name: "Confirm" }).click();
  await expect
    .element(screen.getByRole("alert"))
    .toHaveTextContent("It wasn't confirmed: that can't be done as things stand.");
});

test("one asked of someone else, which grantr showed her, is not hers to confirm", async () => {
  const { serve } = grantr(
    confirmation({
      asked_by: { kind: "person", id: "bob" },
      answerers: { subjects: ["bob"], groups: [], confirmation: true, different_approver: false },
    }),
  );
  const { screen } = await open("/confirm/apr_1", [], serve, ["globex"]);
  await expect
    .element(screen.getByText("Only the person who made the call confirms it."))
    .toBeVisible();
  await expect.element(screen.getByRole("button", { name: "Confirm" })).not.toBeInTheDocument();
});

test("an approval that isn't a confirmation is sent to its page in the app", async () => {
  const { serve } = grantr(
    confirmation({
      answerers: {
        subjects: ["alice"],
        groups: [],
        confirmation: false,
        different_approver: false,
      },
    }),
  );
  const { screen } = await open("/confirm/apr_1", [], serve, ["globex"]);
  await expect
    .element(screen.getByRole("link", { name: "Open its page" }))
    .toHaveAttribute("href", "/portalr/app/t/globex/approvals/apr_1");
});

test("one answered already shows its answer, with nothing to confirm", async () => {
  const { serve } = grantr(
    confirmation({
      state: "approved",
      answer: {
        approved: true,
        arguments_digest: "a".repeat(64),
        at: "2026-11-01T10:00:00Z",
        by: { id: "alice", groups: [], service: false },
        surface: "portalr:confirm",
      },
    }),
  );
  const { screen } = await open("/confirm/apr_1", [], serve, ["globex"]);
  await expect.element(screen.getByText("Approved by")).toBeVisible();
  await expect
    .element(screen.getByRole("textbox", { name: "Type globex to confirm" }))
    .not.toBeInTheDocument();
});

test("one none of her tenants shows is nothing to confirm", async () => {
  const { serve, reads } = grantr(confirmation());
  const { screen } = await open("/confirm/apr_1", [], serve, ["acme"]);
  await expect.element(screen.getByRole("heading", { name: "Nothing to confirm" })).toBeVisible();
  expect(reads).toEqual(["acme"]);
});

test("a failure other than not there is the page's to show, not a tenant to skip", async () => {
  const serve: Serve = async (_request, path) =>
    path.startsWith("/grantr/v1/tenants/")
      ? Response.json({ detail: "down" }, { status: 503 })
      : undefined;
  const { screen } = await open("/confirm/apr_1", [], serve, ["acme", "globex"]);
  await expect
    .element(screen.getByRole("heading", { name: "Nothing to confirm" }))
    .not.toBeInTheDocument();
});
