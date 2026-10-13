/**
 * Audit as a route, over a stubbed grantr: on the rail where grantr allows reading the log, the
 * newest on top, a page back at a time, a filter in the address, and each failure a way on.
 */

import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { page } from "vitest/browser";
import { open as opened } from "./test/admin";

/** The audit reads Audit made, by their query. */
const audits: URLSearchParams[] = [];

/** A log of so many changes by bob: members added, each between two grants. */
const logOf = (length: number) =>
  Array.from({ length }, (_, index) => ({
    seq: index + 1,
    at: "2026-10-13T00:00:00Z",
    by: { kind: "user", id: "bob" },
    tenant: "acme",
    event:
      index % 3 === 0
        ? { type: "member_added", member: { kind: "service_principal", id: `sp_${index + 1}` } }
        : {
            type: "granted",
            grant: {
              role: "viewer",
              on: { kind: "workspace", workspace: "notes" },
              to: { kind: "user", id: `u_${index + 1}` },
              tenant: "acme",
            },
          },
  }));

let log = logOf(60);
/** Whether grantr fails a read of a page before another. */
let failsPagingBack = false;

/** grantr's audit log: `last` before `before_seq`, of the types asked, refusing `actor=nobody`. */
async function audit(request: Request, path: string): Promise<Response | undefined> {
  if (path !== "/grantr/v1/tenants/acme/audit") {
    return undefined;
  }
  const query = new URL(request.url).searchParams;
  audits.push(query);
  if (query.get("actor") === "nobody") {
    return Response.json({ detail: "no such subject" }, { status: 422 });
  }
  if (failsPagingBack && query.has("before_seq")) {
    return Response.json({ detail: "grantr is down" }, { status: 503 });
  }
  const before = Number(query.get("before_seq") ?? Number.POSITIVE_INFINITY);
  const kept = log.filter(
    (entry) =>
      entry.seq < before && (!query.has("type") || query.getAll("type").includes(entry.event.type)),
  );
  return Response.json(kept.slice(Math.max(kept.length - Number(query.get("last")), 0)));
}

const open = (path: string, allowed: readonly string[] = ["grantr:read_audit"]) =>
  opened(path, allowed, audit);

// A desktop's width: the rail beside the page, and the log a table.
beforeEach(async () => {
  await page.viewport(1280, 800);
});

afterEach(() => {
  audits.length = 0;
  log = logOf(60);
  failsPagingBack = false;
  vi.unstubAllGlobals();
});

test("Audit is on the rail where grantr allows reading the log, and not found elsewhere", async () => {
  const { screen } = await open("/t/acme/audit", ["grantr:add_member"]);
  await expect.element(screen.getByText("The audit log isn't yours to read here")).toBeVisible();
  const rail = screen.getByRole("navigation", { name: "Tenant" });
  await expect.element(rail.getByRole("link", { name: "Access" })).toBeVisible();
  await expect.element(rail.getByRole("link", { name: "Audit" })).not.toBeInTheDocument();
  expect(audits).toEqual([]);
});

test("the log opens on the newest changes, and Show more adds the ones before", async () => {
  const { screen } = await open("/t/acme");
  await screen
    .getByRole("navigation", { name: "Tenant" })
    .getByRole("link", { name: "Audit" })
    .click();
  const table = screen.getByRole("table", { name: "Audit log" });
  await expect
    .element(
      table.getByRole("rowheader", { name: "granted viewer on workspace notes to u_60 (person)" }),
    )
    .toBeVisible();
  expect(table.getByRole("rowheader").elements()).toHaveLength(50);
  expect(table.getByRole("rowheader").elements()[0]?.textContent).toMatch(/u_60/);
  await expect.element(screen.getByRole("status")).toHaveTextContent("50 changes shown");
  await screen.getByRole("button", { name: "Show more" }).click();
  await expect
    .element(table.getByRole("rowheader", { name: "added sp_1 (service principal)" }))
    .toBeVisible();
  await expect.element(screen.getByRole("status")).toHaveTextContent("60 changes shown");
  expect(audits.map((query) => query.get("before_seq"))).toEqual([null, "11"]);
  expect(audits.every((query) => query.get("last") === "50")).toBe(true);
  // The newest on top, down to the first.
  expect(table.getByRole("rowheader").elements().at(-1)?.textContent).toBe(
    "added sp_1 (service principal)",
  );
  await expect.element(screen.getByRole("button", { name: "Show more" })).not.toBeInTheDocument();
});

test("a log of exactly one page offers Show more once, and then says it has all", async () => {
  log = logOf(50);
  const { screen } = await open("/t/acme/audit");
  await screen.getByRole("button", { name: "Show more" }).click();
  await expect.element(screen.getByRole("button", { name: "Show more" })).not.toBeInTheDocument();
  await expect.element(screen.getByRole("status")).toHaveTextContent("50 changes shown");
  expect(audits.map((query) => query.get("before_seq"))).toEqual([null, "1"]);
});

test("a filter goes to grantr and into the address, trimmed, and Clear takes it away", async () => {
  const { screen, router } = await open("/t/acme/audit");
  await screen.getByRole("combobox", { name: "Change" }).selectOptions("Members added");
  await screen.getByRole("combobox", { name: "Made by" }).selectOptions("A person");
  await screen.getByRole("textbox", { name: "Their id" }).fill(" bob ");
  await screen.getByRole("button", { name: "Apply" }).click();
  const table = screen.getByRole("table", { name: "Audit log" });
  await expect
    .element(table.getByRole("rowheader", { name: /^granted/ }).first())
    .not.toBeInTheDocument();
  expect(table.getByRole("rowheader").elements()).toHaveLength(20);
  expect(router.state.location.search).toEqual({
    type: "member_added",
    actor_kind: "user",
    actor: "bob",
  });
  const asked = audits.at(-1);
  expect(asked?.getAll("type")).toEqual(["member_added"]);
  expect(asked?.get("actor_kind")).toBe("user");
  expect(asked?.get("actor")).toBe("bob");
  await screen.getByRole("button", { name: "Clear" }).click();
  await expect.element(table.getByRole("rowheader", { name: /^granted/ }).first()).toBeVisible();
});

test("an address naming a maker grantr can't take reads the whole log", async () => {
  const { screen } = await open("/t/acme/audit?actor_kind=service_principal&actor=has:colon");
  await expect.element(screen.getByRole("table", { name: "Audit log" })).toBeVisible();
  // The read uses only what grantr takes: here, nothing of the maker.
  expect(audits.every((query) => !query.has("actor") && !query.has("actor_kind"))).toBe(true);
  // The form shows the filter read, not the address.
  await expect.element(screen.getByRole("combobox", { name: "Made by" })).toHaveValue("");
});

test("a filter grantr refuses says why, and clearing it reads the log again", async () => {
  const { screen, router } = await open("/t/acme/audit?actor_kind=user&actor=nobody");
  await expect
    .element(screen.getByRole("alert"))
    .toHaveTextContent('the server refused the read (422): {"detail":"no such subject"}');
  await screen.getByRole("button", { name: "Clear the filter" }).click();
  await expect.element(screen.getByRole("table", { name: "Audit log" })).toBeVisible();
  expect(router.state.location.search).toEqual({});
});

test("a page before that can't be read says so, and keeps the log shown", async () => {
  failsPagingBack = true;
  const { screen } = await open("/t/acme/audit");
  await screen.getByRole("button", { name: "Show more" }).click();
  await expect
    .element(screen.getByRole("alert"))
    .toHaveTextContent(
      'The changes before these couldn\'t be read: the server refused the read (503): {"detail":"grantr is down"}',
    );
  expect(
    screen.getByRole("table", { name: "Audit log" }).getByRole("rowheader").elements(),
  ).toHaveLength(50);
});

test("on a phone, the log is a list of cards, each named by its change and when", async () => {
  await page.viewport(414, 896);
  log = logOf(1);
  const { screen } = await open("/t/acme/audit");
  const cards = screen.getByRole("list", { name: "Audit log" });
  await expect
    .element(
      cards.getByRole("listitem", {
        name: `added sp_1 (service principal), ${new Date("2026-10-13T00:00:00Z").toLocaleString()}`,
      }),
    )
    .toBeVisible();
  await expect.element(screen.getByRole("table", { name: "Audit log" })).not.toBeInTheDocument();
});
