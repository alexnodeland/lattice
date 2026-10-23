/**
 * Tenants and the deployment's Audit as routes, over a stubbed portalr and grantr: for an operator,
 * every tenant with its spend and budget, a page at a time, a tenant created with its owner by
 * email once confirmed and sent once, and the deployment's audit log.
 */

import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { page, userEvent } from "vitest/browser";
import { open as opened } from "./test/admin";

/** The tenants grantr lists, and what LiteLLM says their teams spend. */
let tenants: string[] = [];
let spend: unknown = { status: "ok", data: [] };
/** What the server answers creating a tenant. */
let creation: () => Response | Promise<Response> = () =>
  Response.json({ tenant: "initech", owner: "dan" }, { status: 201 });
/** The tenant reads, and the creations, made. */
let reads = 0;
const created: { tenant: string; owner_email: string }[] = [];
let audit: { seq: number; at: string; by: unknown; tenant: null; event: unknown }[] = [];
let auditFails = false;

const team = (tenant: string, spent: number, max: number | null = null) => ({
  tenant,
  spend: spent,
  max_budget: max,
  budget_duration: max ? "30d" : null,
});

async function portalr(request: Request, path: string): Promise<Response | undefined> {
  if (path === "/portalr/v1/deployment/tenants") {
    if (request.method === "POST") {
      created.push((await request.json()) as never);
      return creation();
    }
    reads += 1;
    return Response.json({ tenants, spend });
  }
  if (path === "/grantr/v1/audit") {
    if (auditFails) {
      return Response.json({ detail: "grantr is down" }, { status: 503 });
    }
    const query = new URL(request.url).searchParams;
    const before = Number(query.get("before_seq") ?? Number.POSITIVE_INFINITY);
    const kept = audit.filter((entry) => entry.seq < before);
    return Response.json(kept.slice(Math.max(kept.length - Number(query.get("last")), 0)));
  }
  if (path === "/artifactr/v1/workspaces") {
    return Response.json([]);
  }
  return undefined;
}

const open = (path: string) => opened(path, [], portalr);

beforeEach(async () => {
  tenants = ["globex", "acme"];
  spend = { status: "ok", data: [team("acme", 25, 100), team("globex", 3)] };
  creation = () => Response.json({ tenant: "initech", owner: "dan" }, { status: 201 });
  reads = 0;
  created.length = 0;
  audit = [];
  auditFails = false;
  await page.viewport(1280, 900);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const fill = async (
  screen: Awaited<ReturnType<typeof open>>["screen"],
  tenant: string,
  email: string,
) => {
  await screen.getByRole("textbox", { name: "Tenant" }).fill(tenant);
  await screen.getByRole("textbox", { name: "Owner's email" }).fill(email);
};

test("every tenant is listed by name, with its spend and its budget", async () => {
  const { screen } = await open("/deployment/tenants");
  const table = screen.getByRole("table", { name: "Tenants" });
  await expect.element(table.getByRole("row", { name: /acme/ })).toBeVisible();
  const acme = table.getByRole("row", { name: /^acme/ });
  await expect.element(acme).toHaveTextContent("acme$25.00$100.00 over 30 days, 25% spent");
  await expect
    .element(table.getByRole("row", { name: /^globex/ }))
    .toHaveTextContent("globex$3.00No budget set");
  // By name: acme before globex.
  const names = table
    .getByRole("row")
    .elements()
    .slice(1)
    .map((row) => row.textContent ?? "");
  expect(names[0]).toMatch(/^acme/);
});

test("a tenant LiteLLM has no team for says it has no budget", async () => {
  tenants = ["acme", "initech"];
  spend = { status: "ok", data: [team("acme", 1)] };
  const { screen } = await open("/deployment/tenants");
  await expect
    .element(screen.getByRole("table", { name: "Tenants" }).getByRole("row", { name: /^initech/ }))
    .toHaveTextContent("initech–No budget");
});

test("LiteLLM not answering leaves the tenants, and says that spend isn't shown", async () => {
  spend = { status: "unavailable", reason: "litellm answered 502" };
  const { screen } = await open("/deployment/tenants");
  await expect.element(screen.getByRole("table", { name: "Tenants" })).toBeVisible();
  await expect
    .element(screen.getByRole("status").first())
    .toHaveTextContent("LiteLLM isn't answering. Spend and budgets are not shown.");
});

test("LiteLLM not configured is said, and no tenants is said", async () => {
  spend = { status: "unconfigured" };
  tenants = [];
  const { screen } = await open("/deployment/tenants");
  await expect.element(screen.getByText("No tenants yet")).toBeVisible();
  await expect
    .element(screen.getByText(/LiteLLM isn't configured\. Spend and budgets are not shown\./))
    .toBeVisible();
});

test("a few hundred tenants are shown fifty at a time", async () => {
  tenants = Array.from({ length: 120 }, (_, at) => `t${String(at).padStart(3, "0")}`);
  spend = { status: "ok", data: [] };
  const { screen } = await open("/deployment/tenants");
  const rows = () =>
    screen.getByRole("table", { name: "Tenants" }).getByRole("row").elements().length - 1;
  await expect.poll(rows).toBe(50);
  await expect
    .element(screen.getByRole("status").getByText("50 of 120 tenants shown"))
    .toBeInTheDocument();
  await screen.getByRole("button", { name: "Show more" }).click();
  await expect.poll(rows).toBe(100);
  await screen.getByRole("button", { name: "Show more" }).click();
  await expect.poll(rows).toBe(120);
  await expect.element(screen.getByRole("button", { name: "Show more" })).not.toBeInTheDocument();
});

test("someone who isn't an operator isn't shown Tenants", async () => {
  const { screen } = await opened("/deployment/tenants", [], async (_request, path) =>
    path === "/portalr/v1/deployment/tenants"
      ? Response.json({ detail: { type: "forbidden", message: "no" } }, { status: 403 })
      : undefined,
  );
  await expect.element(screen.getByRole("heading", { name: "Tenants" })).not.toBeInTheDocument();
});

test("the rail offers Tenants and Audit to an operator", async () => {
  const { screen } = await open("/deployment");
  const rail = screen.getByRole("navigation", { name: "Deployment" });
  await expect.element(rail.getByRole("link", { name: "Tenants" })).toBeVisible();
  await expect.element(rail.getByRole("link", { name: "Audit" })).toBeVisible();
});

test("creating is not possible until the tenant and the owner's email are filled in", async () => {
  const { screen } = await open("/deployment/tenants");
  const create = screen.getByRole("button", { name: "Create tenant" });
  await expect.element(create).toBeDisabled();
  await fill(screen, "initech", "dan");
  await expect.element(create).toBeDisabled();
  await fill(screen, "a~b", "dan@initech.com");
  await expect.element(create).toBeDisabled();
  await fill(screen, "initech", "dan@initech.com");
  await expect.element(create).toBeEnabled();
});

test("a tenant is confirmed, created once, and shown, and its owner's email is kept nowhere", async () => {
  const { screen } = await open("/deployment/tenants");
  await fill(screen, " initech ", " dan@initech.com ");
  await screen.getByRole("button", { name: "Create tenant" }).click();
  const dialog = screen.getByRole("alertdialog", { name: "Create initech?" });
  await expect.element(dialog).toBeVisible();
  await expect.element(dialog.getByText(/makes dan@initech\.com its first owner/)).toBeVisible();
  // Nothing is sent by asking.
  expect(created).toEqual([]);
  tenants = ["acme", "globex", "initech"];
  await dialog.getByRole("button", { name: "Create the tenant" }).click();
  await expect.element(screen.getByText("initech is created, owned by dan.")).toBeVisible();
  // Starting another tenant puts the last one's status away.
  await screen.getByRole("textbox", { name: "Tenant" }).fill("next");
  await expect
    .element(screen.getByText("initech is created, owned by dan."))
    .not.toBeInTheDocument();
  await screen.getByRole("textbox", { name: "Tenant" }).fill("");
  expect(created).toEqual([{ tenant: "initech", owner_email: "dan@initech.com" }]);
  // The list is read again, with the new tenant in it; the form is empty, and focus is on it.
  await expect
    .element(screen.getByRole("table", { name: "Tenants" }).getByRole("row", { name: /^initech/ }))
    .toBeVisible();
  expect(reads).toBeGreaterThanOrEqual(2);
  await expect.element(screen.getByRole("textbox", { name: "Tenant" })).toHaveValue("");
  await expect.element(screen.getByRole("textbox", { name: "Owner's email" })).toHaveValue("");
  await expect.element(screen.getByRole("textbox", { name: "Tenant" })).toHaveFocus();
  // The email is not in the browser's storage, nor on the page once it is created.
  const stored = JSON.stringify([
    ...Object.entries(localStorage),
    ...Object.entries(sessionStorage),
  ]);
  expect(stored).not.toContain("dan@initech.com");
  expect(document.body.textContent).not.toContain("dan@initech.com");
});

test("a submit while the creation is under way is sent once", async () => {
  let finish: () => void = () => undefined;
  creation = () =>
    new Promise((resolve) => {
      finish = () => resolve(Response.json({ tenant: "initech", owner: "dan" }, { status: 201 }));
    });
  const { screen } = await open("/deployment/tenants");
  await fill(screen, "initech", "dan@initech.com");
  await screen.getByRole("button", { name: "Create tenant" }).click();
  const dialog = screen.getByRole("alertdialog", { name: "Create initech?" });
  await dialog.getByRole("button", { name: "Create the tenant" }).click();
  await userEvent.keyboard("{Enter}");
  await userEvent.keyboard("{Escape}");
  await expect.poll(() => created.length).toBe(1);
  await expect.element(dialog).toBeVisible();
  finish();
  await expect.element(dialog).not.toBeInTheDocument();
  expect(created).toHaveLength(1);
});

test("a tenant that exists is refused in the dialog, which stays, and nothing else is made", async () => {
  creation = () =>
    Response.json({ detail: { type: "invalid", message: "initech exists" } }, { status: 422 });
  const { screen } = await open("/deployment/tenants");
  await fill(screen, "initech", "dan@initech.com");
  await screen.getByRole("button", { name: "Create tenant" }).click();
  const dialog = screen.getByRole("alertdialog", { name: "Create initech?" });
  await dialog.getByRole("button", { name: "Create the tenant" }).click();
  await expect
    .element(dialog.getByRole("alert"))
    .toHaveTextContent("Not created: what was asked for isn't valid.");
  // Still filled in, to change; and nothing says it was created.
  await expect.element(screen.getByText(/is created, owned by/)).not.toBeInTheDocument();
});

test("an owner Supabase couldn't invite is said, without the email", async () => {
  creation = () =>
    Response.json(
      { detail: { type: "invite_failed", message: "supabase answered 500" } },
      { status: 502 },
    );
  const { screen } = await open("/deployment/tenants");
  await fill(screen, "initech", "dan@initech.com");
  await screen.getByRole("button", { name: "Create tenant" }).click();
  const dialog = screen.getByRole("alertdialog", { name: "Create initech?" });
  await dialog.getByRole("button", { name: "Create the tenant" }).click();
  await expect
    .element(dialog.getByRole("alert"))
    .toHaveTextContent(
      "Not created: the invitation couldn't be sent: check the email address, then try again.",
    );
  expect(dialog.getByRole("alert").element().textContent).not.toContain("dan@initech.com");
});

test("a caller who may not create is refused in the dialog", async () => {
  creation = () =>
    Response.json(
      { detail: { type: "forbidden", message: "the caller may not create tenants" } },
      { status: 403 },
    );
  const { screen } = await open("/deployment/tenants");
  await fill(screen, "initech", "dan@initech.com");
  await screen.getByRole("button", { name: "Create tenant" }).click();
  const dialog = screen.getByRole("alertdialog", { name: "Create initech?" });
  await dialog.getByRole("button", { name: "Create the tenant" }).click();
  await expect
    .element(dialog.getByRole("alert"))
    .toHaveTextContent("Not created: you may not do this here.");
});

const entry = (seq: number, id: string) => ({
  seq,
  at: "2026-10-14T00:00:00Z",
  by: { kind: "user", id: "ops" },
  tenant: null,
  event: {
    type: "granted",
    grant: { role: "operator", on: { kind: "deployment" }, to: { kind: "user", id }, tenant: null },
  },
});

test("the deployment's audit log is read newest first, a page back at a time", async () => {
  audit = Array.from({ length: 60 }, (_, at) => entry(at + 1, `u${at + 1}`));
  const { screen } = await open("/deployment/audit");
  const table = screen.getByRole("table", { name: "Deployment audit log" });
  await expect.element(table).toBeVisible();
  const rows = () => table.getByRole("row").elements().length - 1;
  await expect.poll(rows).toBe(50);
  expect(table.getByRole("row").elements()[1]?.textContent).toContain("u60");
  await screen.getByRole("button", { name: "Show more" }).click();
  await expect.poll(rows).toBe(60);
  await expect.element(screen.getByRole("button", { name: "Show more" })).not.toBeInTheDocument();
});

test("a deployment with no operator changes yet says so", async () => {
  const { screen } = await open("/deployment/audit");
  await expect.element(screen.getByText("No changes yet")).toBeVisible();
});

test("the deployment's audit log not being readable is a way on", async () => {
  auditFails = true;
  const { screen } = await open("/deployment/audit");
  await expect
    .element(screen.getByRole("heading", { name: "The deployment's audit log couldn't be read" }))
    .toHaveFocus();
  // Try again reads it again: once it can be, the log is there.
  auditFails = false;
  await screen.getByRole("button", { name: "Try again" }).click();
  await expect.element(screen.getByText("No changes yet")).toBeVisible();
});
