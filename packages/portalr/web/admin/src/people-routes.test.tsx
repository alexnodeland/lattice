/**
 * People by email, in the screens that show them: Members, Groups, Grants and Audit. The server
 * names those the reader may see; an id it leaves out, or a server that fails, shows as a short
 * id, never as an error, and no email reaches an address, a storage or a request (portalr
 * ADR-0038).
 */

import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { page } from "vitest/browser";
import { TENANT_ACTIONS } from "./access";
import { open as opened } from "./test/admin";

const ADA = "3f2a91c4-1111-4222-8333-444455556666";
const BEN = "9b7d00ee-1111-4222-8333-444455556666";
const GONE = "c0ffee00-1111-4222-8333-444455556666";
const EMAILS: Record<string, string> = { [ADA]: "ada@acme.test", [BEN]: "ben@acme.test" };

/** What each read of people asked: their ids, and the tenant it named. */
const asked: { readonly ids: string[]; readonly tenant: string | null }[] = [];
/** Every request's URL, to hold none to an email. */
const urls: string[] = [];
/** Held until released: globex's answer, so a test can look at what shows meanwhile. */
let globex: { readonly promise: Promise<void> } | null = null;
/** Whether the server fails every read of people. */
let failing = false;

const at = "2026-10-13T00:00:00Z";
const user = (id: string) => ({ kind: "user", id });
const grant = (role: string, to: unknown, on: unknown) => ({ role, on, to, tenant: "acme" });

async function serve(request: Request, path: string): Promise<Response | undefined> {
  urls.push(request.url);
  if (path === "/portalr/v1/people") {
    const ids = new URL(request.url).searchParams.getAll("id");
    asked.push({ ids, tenant: request.headers.get("x-tenant") });
    if (request.headers.get("x-tenant") === "globex") {
      await globex?.promise;
      return Response.json({ people: { [ADA]: "ada@globex.test" } });
    }
    if (failing) {
      return Response.json({ detail: "down" }, { status: 502 });
    }
    return Response.json({
      people: Object.fromEntries(ids.filter((id) => id in EMAILS).map((id) => [id, EMAILS[id]])),
    });
  }
  if (path === "/grantr/v1/tenants/globex/members") {
    return Response.json([user(ADA)]);
  }
  if (path === "/grantr/v1/tenants/acme/members") {
    return Response.json([
      { kind: "service_principal", id: "ci" },
      user(GONE),
      user(BEN),
      user(ADA),
    ]);
  }
  if (path === "/grantr/v1/tenants/acme/groups") {
    return Response.json({ ops: [user(ADA), user(GONE), { kind: "service_principal", id: "ci" }] });
  }
  if (path === "/grantr/v1/tenants/acme/grants") {
    return Response.json([
      grant("editor", user(ADA), { kind: "workspace", workspace: "ws_1" }),
      grant("viewer", user(GONE), { kind: "workspace", workspace: "ws_1" }),
    ]);
  }
  if (path === "/grantr/v1/tenants/acme/roles") {
    return Response.json([]);
  }
  if (path === "/grantr/v1/catalog") {
    return Response.json({
      roles: [
        { name: "editor", kinds: ["workspace"] },
        { name: "viewer", kinds: ["workspace"] },
      ],
      custom_actions: [],
      custom_kinds: ["workspace"],
    });
  }
  if (path === "/portalr/v1/deployment/tenants") {
    return Response.json({ tenants: ["acme"], spend: { status: "unconfigured" } });
  }
  if (path === "/grantr/v1/audit") {
    return Response.json([
      {
        seq: 1,
        at,
        by: user(ADA),
        tenant: null,
        event: { type: "granted", grant: grant("operator", user(BEN), { kind: "deployment" }) },
      },
      {
        seq: 2,
        at,
        by: null,
        tenant: null,
        event: { type: "granted", grant: grant("operator", user(GONE), { kind: "deployment" }) },
      },
      {
        seq: 3,
        at,
        by: user(ADA),
        tenant: null,
        event: { type: "deployment_tenant_created", tenant: "globex", owner: GONE },
      },
    ]);
  }
  if (path === "/grantr/v1/tenants/acme/audit") {
    return Response.json([
      {
        seq: 1,
        at,
        by: user(ADA),
        tenant: "acme",
        event: { type: "member_added", member: user(BEN) },
      },
      {
        seq: 2,
        at,
        by: user(GONE),
        tenant: "acme",
        event: { type: "member_added", member: user(GONE) },
      },
      {
        seq: 3,
        at,
        by: user(BEN),
        tenant: "acme",
        event: {
          type: "granted",
          grant: grant("viewer", user(ADA), { kind: "workspace", workspace: "ws_1" }),
        },
      },
    ]);
  }
  return undefined;
}

const open = (path: string, config?: Parameters<typeof opened>[4]) =>
  opened(path, TENANT_ACTIONS, serve, ["acme"], config);

beforeEach(async () => {
  await page.viewport(1280, 800);
});

afterEach(() => {
  asked.length = 0;
  urls.length = 0;
  failing = false;
  globex = null;
  vi.unstubAllGlobals();
});

test("Members shows people by their email, a short id for one the server leaves out", async () => {
  const { screen } = await open("/t/acme/access/members");
  const rows = screen.getByRole("table", { name: "Members" }).getByRole("rowheader");
  await expect.element(rows.first()).toHaveTextContent("ada@acme.test");
  expect(rows.elements().map((row) => row.textContent)).toEqual([
    "ada@acme.test",
    "ben@acme.test",
    "c0ffee00…",
    "ci",
  ]);
  await expect.element(screen.getByRole("button", { name: "Remove ada@acme.test" })).toBeVisible();
  await expect.element(screen.getByRole("button", { name: "Remove c0ffee00…" })).toBeVisible();
});

test("the emails are asked for once, for people alone, in the tenant", async () => {
  const { screen } = await open("/t/acme/access/members");
  await expect.element(screen.getByRole("rowheader", { name: "ada@acme.test" })).toBeVisible();
  expect(asked).toEqual([{ ids: [ADA, BEN, GONE].sort(), tenant: "acme" }]);
});

test("the remove dialog names the person as the row does", async () => {
  const { screen } = await open("/t/acme/access/members");
  await screen.getByRole("button", { name: "Remove ben@acme.test" }).click();
  const dialog = screen.getByRole("alertdialog", { name: "Remove ben@acme.test from acme?" });
  await expect.element(dialog).toBeVisible();
  expect(dialog.element().textContent).toContain("ben@acme.test loses every role in acme");
});

test("a server that fails to name people leaves short ids, and no error", async () => {
  failing = true;
  const { screen } = await open("/t/acme/access/members");
  const rows = screen.getByRole("table", { name: "Members" }).getByRole("rowheader");
  await expect.element(rows.first()).toHaveTextContent("3f2a91c4…");
  expect(rows.elements().map((row) => row.textContent)).toEqual([
    "3f2a91c4…",
    "9b7d00ee…",
    "c0ffee00…",
    "ci",
  ]);
  await expect.element(screen.getByRole("alert")).not.toBeInTheDocument();
});

test("without a people route in the deployment, the server is not asked", async () => {
  const { screen } = await open("/t/acme/access/members", { people: false });
  await expect.element(screen.getByRole("rowheader", { name: "3f2a91c4…" })).toBeVisible();
  expect(asked).toEqual([]);
});

test("Groups lists a group's people by email, a short id for the rest", async () => {
  const { screen } = await open("/t/acme/access/groups");
  await expect
    .element(
      screen.getByRole("cell", {
        name: "ada@acme.test (person), c0ffee00… (person), ci (service principal)",
      }),
    )
    .toBeVisible();
  await screen.getByRole("button", { name: "Change ops' members" }).click();
  await expect
    .element(screen.getByRole("checkbox", { name: "ben@acme.test (person)" }))
    .toBeVisible();
});

test("Grants names whom each is to, and the revoke dialog says it the same way", async () => {
  const { screen } = await open("/t/acme/access/grants");
  await expect
    .element(screen.getByRole("rowheader", { name: "ada@acme.test (person)" }))
    .toBeVisible();
  await expect.element(screen.getByRole("rowheader", { name: "c0ffee00… (person)" })).toBeVisible();
  const choices = screen.getByRole("combobox", { name: "To" });
  await expect
    .element(choices.getByRole("option", { name: "ben@acme.test (person)" }))
    .toBeInTheDocument();
});

test("Audit says who made a change and whom it was about, by email", async () => {
  const { screen } = await open("/t/acme/audit");
  const log = screen.getByRole("table", { name: "Audit log" });
  await expect
    .element(log.getByRole("rowheader", { name: "added ben@acme.test (person)" }))
    .toBeVisible();
  await expect
    .element(log.getByRole("rowheader", { name: "added c0ffee00… (person)" }))
    .toBeVisible();
  await expect
    .element(
      log.getByRole("rowheader", { name: /^granted viewer on workspace ws_1 to ada@acme.test/ }),
    )
    .toBeVisible();
  await expect.element(log.getByRole("cell", { name: "ada@acme.test (person)" })).toBeVisible();
  await expect.element(log.getByRole("cell", { name: "c0ffee00… (person)" })).toBeVisible();
});

test("no email is in an address, a request's URL, or the browser's storage", async () => {
  const { screen, router } = await open("/t/acme/audit");
  await expect.element(screen.getByRole("cell", { name: "ada@acme.test (person)" })).toBeVisible();
  expect(router.state.location.href).not.toContain("@");
  expect(urls.filter((url) => url.includes("@"))).toEqual([]);
  expect(JSON.stringify({ ...localStorage, ...sessionStorage })).not.toContain("@acme.test");
});

test("the deployment's audit log, for an operator, names people in no tenant", async () => {
  const { screen } = await open("/deployment/audit");
  const log = screen.getByRole("table", { name: "Deployment audit log" });
  await expect
    .element(log.getByRole("rowheader", { name: /to ben@acme\.test \(person\)$/ }))
    .toBeVisible();
  await expect
    .element(log.getByRole("rowheader", { name: /to c0ffee00… \(person\)$/ }))
    .toBeVisible();
  await expect
    .element(log.getByRole("cell", { name: "ada@acme.test (person)" }).first())
    .toBeVisible();
  expect(asked.at(-1)?.tenant).toBeNull();
});

test("the deployment's audit log shows who created which tenant, and for whom", async () => {
  const { screen } = await open("/deployment/audit");
  const log = screen.getByRole("table", { name: "Deployment audit log" });
  await expect
    .element(
      log.getByRole("rowheader", {
        name: "created the tenant globex, owned by c0ffee00… (person)",
      }),
    )
    .toBeVisible();
  // The owner is named too: the creation's owner is among the ids asked after.
  expect(asked.at(-1)?.ids).toContain(GONE);
});

test("another tenant opened on the same screen is not shown the first tenant's emails", async () => {
  let release: () => void = () => undefined;
  globex = {
    promise: new Promise<void>((resolve) => {
      release = resolve;
    }),
  };
  const { screen, router } = await opened("/t/acme/access/members", TENANT_ACTIONS, serve, [
    "acme",
    "globex",
  ]);
  await expect.element(screen.getByRole("rowheader", { name: "ada@acme.test" })).toBeVisible();
  await router.navigate({ to: "/t/$tenant/access/members", params: { tenant: "globex" } });
  // globex has not answered: the same person is their short id, not acme's email for them.
  const rows = screen.getByRole("table", { name: "Members" }).getByRole("rowheader");
  await expect.element(rows.first()).toHaveTextContent("3f2a91c4…");
  expect(rows.elements().map((row) => row.textContent)).toEqual(["3f2a91c4…"]);
  expect(document.body.textContent).not.toContain("ada@acme.test");
  release();
  await expect.element(screen.getByRole("rowheader", { name: "ada@globex.test" })).toBeVisible();
});
