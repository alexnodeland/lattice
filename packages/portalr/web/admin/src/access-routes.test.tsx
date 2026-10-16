/**
 * Access as a route, over a stubbed grantr: what each part shows for what grantr allows, the
 * part not allowed said in the tenant's frame, and a key's secret gone once its screen is left.
 */

import { choose, optionsOf } from "@portalr/ui/testing";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { page } from "vitest/browser";
import { TENANT_ACTIONS } from "./access";
import { open as opened } from "./test/admin";

/** Each change Access sent: its method and path, and its body. */
const sent: { readonly to: string; readonly body: unknown }[] = [];
const keyring = [{ id: "k_1", principal: { kind: "service_principal", id: "ci" } }];

/** grantr, as far as Access reads it, past who alice is and what she may: the harness answers those. */
async function access(request: Request, path: string): Promise<Response | undefined> {
  if (request.method === "PUT" || request.method === "DELETE") {
    sent.push({ to: `${request.method} ${path}`, body: await request.text() });
    return Response.json({ at: "2026-10-13T00:00:00Z", by: null, seq: 2, tenant: "acme" });
  }
  if (request.method === "POST" && path.endsWith("/grants")) {
    const body = await request.text();
    sent.push({ to: `POST ${path}`, body });
    // grantr refuses granting editor to bob, who holds it.
    return body.includes('"editor"') && body.includes('"bob"')
      ? Response.json({ detail: "bob holds editor there already" }, { status: 422 })
      : Response.json({ at: "2026-10-13T00:00:00Z", by: null, seq: 3, tenant: "acme" });
  }
  if (path === "/grantr/v1/tenants/acme/revocations") {
    const body = await request.text();
    sent.push({ to: `POST ${path}`, body });
    // grantr refuses revoking editor: as if alice held less than it gives.
    return body.includes('"editor"')
      ? Response.json(
          { detail: "holds less than editor gives: reflexr:retry_run" },
          { status: 403 },
        )
      : Response.json({ at: "2026-10-13T00:00:00Z", by: null, seq: 4, tenant: "acme" });
  }
  if (path === "/grantr/v1/catalog") {
    return Response.json({
      roles: [
        { name: "owner", kinds: ["tenant"] },
        { name: "editor", kinds: ["workspace"] },
        { name: "viewer", kinds: ["workspace", "thread", "artifact", "rule"] },
      ],
      custom_actions: ["reflexr:retry_run", "reflexr:skip_run"],
      custom_kinds: ["workspace", "thread", "artifact", "rule"],
    });
  }
  if (path === "/grantr/v1/tenants/acme/roles") {
    return Response.json([{ name: "triager", actions: ["reflexr:retry_run", "reflexr:skip_run"] }]);
  }
  if (path === "/grantr/v1/tenants/acme/grants") {
    return Response.json([
      {
        role: "owner",
        on: { kind: "tenant" },
        to: { kind: "user", id: "alice" },
        tenant: "acme",
      },
      { role: "member", on: { kind: "tenant" }, to: { kind: "user", id: "bob" }, tenant: "acme" },
      {
        role: "viewer",
        on: { kind: "thread", workspace: "ws_1", id: "t_1" },
        to: { kind: "group", id: "ops" },
        tenant: "acme",
      },
      {
        role: "editor",
        on: { kind: "workspace", workspace: "ws_1" },
        to: { kind: "user", id: "bob" },
        tenant: "acme",
      },
    ]);
  }
  if (path === "/grantr/v1/tenants/acme/members") {
    return Response.json([
      { kind: "service_principal", id: "ci" },
      { kind: "user", id: "bob" },
      { kind: "user", id: "alice" },
    ]);
  }
  if (path === "/grantr/v1/tenants/acme/groups") {
    return Response.json({ ops: [{ kind: "user", id: "bob" }] });
  }
  if (path === "/grantr/v1/tenants/acme/keys" && request.method === "GET") {
    return Response.json(keyring);
  }
  if (path === "/grantr/v1/tenants/acme/keys") {
    keyring.push({ id: "k_2", principal: { kind: "service_principal", id: "ci" } });
    return Response.json({
      key: "k_2.s3cr3t",
      entry: {
        at: "2026-10-13T00:00:00Z",
        by: null,
        seq: 1,
        tenant: "acme",
        event: {
          type: "key_issued",
          key: "k_2",
          principal: { kind: "service_principal", id: "ci" },
        },
      },
    });
  }
  return undefined;
}

const open = (path: string, allowed: readonly string[]) => opened(path, allowed, access);

// A desktop's width: the rail beside the page, and each part a table.
beforeEach(async () => {
  await page.viewport(1280, 800);
});

afterEach(() => {
  sent.length = 0;
  keyring.length = 1;
  vi.unstubAllGlobals();
});

test("without removing or revoking, Members has no Remove and Keys no Revoke", async () => {
  const { screen, router } = await open("/t/acme/access/members", [
    "grantr:add_member",
    "grantr:issue_key",
  ]);
  const members = screen.getByRole("table", { name: "Members" });
  await expect.element(members.getByRole("rowheader", { name: "bob" })).toBeVisible();
  await expect.element(screen.getByRole("button", { name: /^Remove/ })).not.toBeInTheDocument();
  await router.navigate({ to: "/t/$tenant/access/keys", params: { tenant: "acme" } });
  await expect.element(screen.getByRole("rowheader", { name: "k_1" })).toBeVisible();
  await expect.element(screen.getByRole("button", { name: /^Revoke/ })).not.toBeInTheDocument();
});

test("people come first, and no one is offered their own removal", async () => {
  const { screen } = await open("/t/acme/access/members", TENANT_ACTIONS);
  const rows = screen.getByRole("table", { name: "Members" }).getByRole("rowheader");
  await expect.element(rows.first()).toHaveTextContent("alice");
  expect(rows.elements().map((row) => row.textContent)).toEqual(["alice", "bob", "ci"]);
  await expect.element(screen.getByRole("button", { name: "Remove bob" })).toBeVisible();
  await expect
    .element(screen.getByRole("button", { name: "Remove alice" }))
    .not.toBeInTheDocument();
});

test("a part grantr doesn't allow, opened by its address, is not found in the frame", async () => {
  const { screen } = await open("/t/acme/access/keys", ["grantr:add_member"]);
  await expect.element(screen.getByText("There's no such part of Access here")).toBeVisible();
  await expect.element(screen.getByRole("navigation", { name: "Tenant" })).toBeVisible();
  const parts = screen.getByRole("navigation", { name: "Access" });
  await expect.element(parts.getByRole("link", { name: "Members" })).toBeVisible();
  await expect.element(parts.getByRole("link", { name: "Keys" })).not.toBeInTheDocument();
});

test("with no part allowed, Access is not on the rail", async () => {
  const { screen } = await open("/t/acme", ["grantr:remove_member"]);
  const rail = screen.getByRole("navigation", { name: "Tenant" });
  await expect.element(rail.getByRole("link", { name: "Home" })).toBeVisible();
  await expect.element(rail.getByRole("link", { name: "Access" })).not.toBeInTheDocument();
});

test("a key's secret is gone once Keys is left and opened again", async () => {
  const { screen, router } = await open("/t/acme/access/keys", TENANT_ACTIONS);
  await screen.getByRole("button", { name: "Issue" }).click();
  const secret = screen.getByRole("textbox", { name: "The key" });
  await expect.element(secret).toHaveValue("k_2.s3cr3t");
  await expect.element(secret).toHaveAttribute("spellcheck", "false");
  await router.navigate({ to: "/t/$tenant/access/members", params: { tenant: "acme" } });
  await router.navigate({ to: "/t/$tenant/access/keys", params: { tenant: "acme" } });
  await expect.element(screen.getByRole("rowheader", { name: "k_1" })).toBeVisible();
  await expect.element(screen.getByRole("textbox", { name: "The key" })).not.toBeInTheDocument();
});

test("Done clears a key's secret", async () => {
  const { screen } = await open("/t/acme/access/keys", TENANT_ACTIONS);
  await screen.getByRole("button", { name: "Issue" }).click();
  await expect.element(screen.getByRole("textbox", { name: "The key" })).toBeVisible();
  await screen.getByRole("button", { name: "Done" }).click();
  await expect.element(screen.getByRole("textbox", { name: "The key" })).not.toBeInTheDocument();
});

test("Create refuses a group's name that is taken, rather than replace its members", async () => {
  const { screen } = await open("/t/acme/access/groups", TENANT_ACTIONS);
  await screen.getByRole("textbox", { name: "Group" }).fill("ops");
  await screen.getByRole("button", { name: "Create the group" }).click();
  await expect
    .element(screen.getByRole("alert"))
    .toHaveTextContent("Not saved: ops is a group already. Change its members from its row.");
  expect(sent).toEqual([]);
});

test("Change members starts from the group's members, and confirms whom it takes out", async () => {
  const { screen } = await open("/t/acme/access/groups", TENANT_ACTIONS);
  await expect.element(screen.getByRole("cell", { name: "bob (person)" })).toBeVisible();
  await screen.getByRole("button", { name: "Change ops' members" }).click();
  const bob = screen.getByRole("checkbox", { name: "bob (person)" });
  await expect.element(bob).toBeChecked();
  await screen.getByRole("checkbox", { name: "ci (service principal)" }).click();
  await bob.click();
  await screen.getByRole("button", { name: "Save the group" }).click();
  const dialog = screen.getByRole("alertdialog", { name: "Take this member out of ops?" });
  await expect
    .element(
      dialog.getByText(
        "bob (person) loses every role granted to ops, and keeps those granted to them.",
      ),
    )
    .toBeVisible();
  await dialog.getByRole("button", { name: "Save the group" }).click();
  await expect.element(screen.getByRole("status")).toHaveTextContent("ops has 1 member.");
  expect(sent).toEqual([
    {
      to: "PUT /grantr/v1/tenants/acme/groups/ops",
      body: JSON.stringify({ members: [{ kind: "service_principal", id: "ci" }] }),
    },
  ]);
});

test("without reading members, a group's members are typed, and checked before sending", async () => {
  const { screen } = await open("/t/acme/access/groups", ["grantr:manage_groups"]);
  await screen.getByRole("textbox", { name: "Group" }).fill("eng");
  const typed = screen.getByRole("textbox", { name: /^Members/ });
  await typed.fill("user:bob, ci");
  await screen.getByRole("button", { name: "Create the group" }).click();
  await expect
    .element(screen.getByRole("alert"))
    .toHaveTextContent("Not saved: Write each member as user:id or service_principal:id, not ci.");
  await typed.fill("user:bob, service_principal:ci");
  await screen.getByRole("button", { name: "Create the group" }).click();
  await expect.element(screen.getByRole("status")).toHaveTextContent("eng has 2 members.");
});

test("revoking the key just issued clears its secret", async () => {
  const { screen } = await open("/t/acme/access/keys", TENANT_ACTIONS);
  await screen.getByRole("button", { name: "Issue" }).click();
  await expect.element(screen.getByRole("textbox", { name: "The key" })).toBeVisible();
  await screen.getByRole("button", { name: "Revoke k_2" }).click();
  await screen.getByRole("alertdialog").getByRole("button", { name: "Revoke" }).click();
  await expect.element(screen.getByRole("textbox", { name: "The key" })).not.toBeInTheDocument();
});

test("without defining roles or granting, Roles and Grants aren't parts", async () => {
  const { screen } = await open("/t/acme/access/members", ["grantr:add_member"]);
  const parts = screen.getByRole("navigation", { name: "Access" });
  await expect.element(parts.getByRole("link", { name: "Members" })).toBeVisible();
  await expect.element(parts.getByRole("link", { name: "Roles" })).not.toBeInTheDocument();
  await expect.element(parts.getByRole("link", { name: "Grants" })).not.toBeInTheDocument();
});

test("with defining roles and granting, Roles and Grants are parts", async () => {
  const { screen } = await open("/t/acme/access/roles", TENANT_ACTIONS);
  const parts = screen.getByRole("navigation", { name: "Access" });
  await expect.element(parts.getByRole("link", { name: "Roles" })).toBeVisible();
  await parts.getByRole("link", { name: "Grants" }).click();
  await expect.element(screen.getByRole("heading", { name: "Grant a role" })).toBeVisible();
});

test("Roles lists the catalog's roles and the custom ones, and refuses a name taken", async () => {
  const { screen } = await open("/t/acme/access/roles", TENANT_ACTIONS);
  const builtIn = screen.getByRole("table", { name: "Built-in roles" });
  await expect.element(builtIn.getByRole("rowheader", { name: "viewer" })).toBeVisible();
  await expect
    .element(builtIn.getByRole("cell", { name: "workspace, thread, artifact, rule" }))
    .toBeVisible();
  const custom = screen.getByRole("table", { name: "Custom roles" });
  await expect.element(custom.getByRole("rowheader", { name: "triager" })).toBeVisible();
  const reflexr = screen.getByRole("group", { name: "reflexr" });
  await expect.element(reflexr.getByRole("checkbox", { name: "reflexr:retry_run" })).toBeVisible();
  await screen.getByRole("textbox", { name: "Role" }).fill("triager");
  await screen.getByRole("checkbox", { name: "reflexr:retry_run" }).click();
  await screen.getByRole("button", { name: "Create the role" }).click();
  await expect
    .element(screen.getByRole("alert"))
    .toHaveTextContent("Not saved: triager is a role already. Change its actions from its row.");
  expect(sent).toEqual([]);
});

test("Change actions starts from the role's, and confirms the actions it takes away", async () => {
  const { screen } = await open("/t/acme/access/roles", TENANT_ACTIONS);
  await screen.getByRole("button", { name: "Change triager's actions" }).click();
  const heading = screen.getByRole("heading", { name: "Change triager's actions" });
  await expect.element(heading).toHaveFocus();
  await expect
    .element(screen.getByText("An action added here is added wherever triager is granted."))
    .toBeVisible();
  const skip = screen.getByRole("checkbox", { name: "reflexr:skip_run" });
  await expect.element(skip).toBeChecked();
  await skip.click();
  await screen.getByRole("button", { name: "Save the role" }).click();
  const dialog = screen.getByRole("alertdialog", { name: "Take this action from triager?" });
  await expect
    .element(
      dialog.getByText("Whoever holds triager loses reflexr:skip_run, wherever it is granted."),
    )
    .toBeVisible();
  await dialog.getByRole("button", { name: "Save the role" }).click();
  await expect.element(screen.getByRole("status")).toHaveTextContent("triager holds 1 action.");
  expect(sent).toEqual([
    {
      to: "PUT /grantr/v1/tenants/acme/roles/triager",
      body: JSON.stringify({ actions: ["reflexr:retry_run"] }),
    },
  ]);
});

test("deleting a custom role says its grants go with it", async () => {
  const { screen } = await open("/t/acme/access/roles", TENANT_ACTIONS);
  await screen.getByRole("button", { name: "Delete triager" }).click();
  const dialog = screen.getByRole("alertdialog", { name: "Delete the role triager?" });
  await expect.element(dialog.getByText("Every grant of triager goes with it.")).toBeVisible();
  await dialog.getByRole("button", { name: "Delete" }).click();
  await expect.element(dialog).not.toBeInTheDocument();
  expect(sent).toEqual([{ to: "DELETE /grantr/v1/tenants/acme/roles/triager", body: "" }]);
});

test("Grants groups the tenant's grants and each workspace's, each named by whom and what", async () => {
  const { screen } = await open("/t/acme/access/grants", TENANT_ACTIONS);
  // Each place is headed, visibly, and its table named by its heading.
  await expect.element(screen.getByRole("heading", { name: "The tenant" })).toBeVisible();
  await expect.element(screen.getByRole("heading", { name: "Workspace ws_1" })).toBeVisible();
  const tenant = screen.getByRole("table", { name: "The tenant" });
  await expect
    .element(tenant.getByRole("row", { name: "alice (person) as owner on the tenant" }))
    .toBeVisible();
  const workspace = screen.getByRole("table", { name: "Workspace ws_1" });
  const rows = workspace
    .getByRole("rowheader")
    .elements()
    .map((row) => row.textContent);
  // The workspace's own grants before its items'.
  expect(rows).toEqual(["bob (person)", "ops (group)"]);
  await expect.element(screen.getByRole("cell", { name: "member" })).not.toBeInTheDocument();
  // The tenant's table doesn't say "the tenant" again; a workspace's names only its items.
  await expect.element(tenant.getByRole("columnheader", { name: "On" })).not.toBeInTheDocument();
  await expect.element(workspace.getByRole("cell", { name: "thread t_1" })).toBeVisible();
  await expect.element(workspace.getByRole("cell", { name: "the workspace" })).toBeVisible();
  // The tenant's one owner is kept: grantr refuses taking the last.
  await expect
    .element(screen.getByRole("button", { name: /^Revoke alice \(person\) as owner/ }))
    .not.toBeInTheDocument();
});

test("on a phone, each place's grants are a list named by its heading", async () => {
  await page.viewport(390, 844);
  const { screen } = await open("/t/acme/access/grants", TENANT_ACTIONS);
  await expect.element(screen.getByRole("list", { name: "Workspace ws_1" })).toBeVisible();
  await expect
    .element(screen.getByRole("table", { name: "Workspace ws_1" }))
    .not.toBeInTheDocument();
});

test("a group made the tenant's admin is named so in the question", async () => {
  const { screen } = await open("/t/acme/access/grants", TENANT_ACTIONS);
  await choose(screen, "Role", "owner");
  await choose(screen, "On", "tenant");
  await choose(screen, "To", "ops (group)");
  await screen.getByRole("button", { name: "Grant", exact: true }).click();
  await expect
    .element(screen.getByRole("alertdialog", { name: "Make the group ops owner of acme?" }))
    .toBeVisible();
});

test("the form starts on no role and no one, and a role chooses where again", async () => {
  const { screen } = await open("/t/acme/access/grants", TENANT_ACTIONS);
  await expect
    .element(screen.getByRole("combobox", { name: "Role" }))
    .toHaveTextContent("Choose a role…");
  await expect
    .element(screen.getByRole("combobox", { name: "To" }))
    .toHaveTextContent("Choose whom…");
  await choose(screen, "Role", "viewer");
  await choose(screen, "On", "thread");
  await expect.element(screen.getByRole("combobox", { name: "Workspace" })).toBeVisible();
  await expect.element(screen.getByRole("textbox", { name: "The thread's id" })).toBeVisible();
  await choose(screen, "Role", "owner");
  await expect
    .element(screen.getByRole("combobox", { name: "On" }))
    .toHaveTextContent("Choose where…");
  await expect.element(screen.getByRole("combobox", { name: "Workspace" })).not.toBeInTheDocument();
  await expect
    .element(screen.getByRole("textbox", { name: "The thread's id" }))
    .not.toBeInTheDocument();
});

test("a custom role is granted where custom roles may be, and the ids are trimmed", async () => {
  const { screen } = await open("/t/acme/access/grants", TENANT_ACTIONS);
  await choose(screen, "Role", "triager");
  expect(await optionsOf(screen, "On")).toEqual([
    "Choose where…",
    "workspace",
    "thread",
    "artifact",
    "rule",
  ]);
  await choose(screen, "On", "workspace");
  await screen.getByRole("combobox", { name: "Workspace" }).fill(" ws_1 ");
  await choose(screen, "To", "ops (group)");
  await screen.getByRole("button", { name: "Grant", exact: true }).click();
  await expect
    .element(screen.getByRole("status"))
    .toHaveTextContent("ops (group) holds triager on workspace ws_1.");
  expect(sent).toEqual([
    {
      to: "POST /grantr/v1/tenants/acme/grants",
      body: JSON.stringify({
        role: "triager",
        on: { kind: "workspace", workspace: "ws_1" },
        to: { kind: "group", id: "ops" },
      }),
    },
  ]);
});

test("granting a role that runs the tenant is confirmed first", async () => {
  const { screen } = await open("/t/acme/access/grants", TENANT_ACTIONS);
  await choose(screen, "Role", "owner");
  await choose(screen, "On", "tenant");
  await choose(screen, "To", "bob (person)");
  // The trigger sits at the form's start, as Grant does; the question names whom it makes owner.
  const trigger = screen.getByRole("button", { name: "Grant", exact: true });
  await expect.element(trigger).toBeVisible();
  const form = trigger.element().closest("form")?.getBoundingClientRect();
  const placed = trigger.element().getBoundingClientRect();
  expect(placed.width).toBeLessThan((form?.width ?? 0) / 2);
  expect(placed.left).toBeCloseTo(form?.left ?? Number.NaN, 0);
  await trigger.click();
  const dialog = screen.getByRole("alertdialog", { name: "Make bob owner of acme?" });
  expect(sent).toEqual([]);
  await dialog.getByRole("button", { name: "Grant owner" }).click();
  await expect
    .element(screen.getByRole("status"))
    .toHaveTextContent("bob (person) holds owner on the tenant.");
  expect(sent.at(-1)?.body).toBe(
    JSON.stringify({ role: "owner", on: { kind: "tenant" }, to: { kind: "user", id: "bob" } }),
  );
});

test("a refused grant says why, and keeps what was entered", async () => {
  const { screen } = await open("/t/acme/access/grants", TENANT_ACTIONS);
  await choose(screen, "Role", "editor");
  await choose(screen, "On", "workspace");
  await screen.getByRole("combobox", { name: "Workspace" }).fill("ws_1");
  await choose(screen, "To", "bob (person)");
  await screen.getByRole("button", { name: "Grant", exact: true }).click();
  await expect
    .element(screen.getByRole("alert"))
    .toHaveTextContent("Not granted: bob holds editor there already");
  await expect.element(screen.getByRole("combobox", { name: "Workspace" })).toHaveValue("ws_1");
  await expect
    .element(screen.getByRole("combobox", { name: "To" }))
    .toHaveTextContent("bob (person)");
});

test("without groups to read, whom is typed as kind:id", async () => {
  const { screen } = await open("/t/acme/access/grants", ["grantr:grant", "grantr:add_member"]);
  await choose(screen, "Role", "viewer");
  await choose(screen, "On", "workspace");
  await screen.getByRole("combobox", { name: "Workspace" }).fill("ws_1");
  const to = screen.getByRole("combobox", { name: /^To, as user:id/ });
  await to.fill("ops");
  await screen.getByRole("button", { name: "Grant", exact: true }).click();
  await expect
    .element(screen.getByRole("alert"))
    .toHaveTextContent(
      "Not granted: name the role, where, and whom, as user:id, service_principal:id or group:id",
    );
  expect(sent).toEqual([]);
  await to.fill(" group:ops ");
  await screen.getByRole("button", { name: "Grant", exact: true }).click();
  await expect
    .element(screen.getByRole("status"))
    .toHaveTextContent("ops (group) holds viewer on workspace ws_1.");
});

test("without deleting the tenant, owner isn't offered, nor its grants' Revoke", async () => {
  const { screen } = await open("/t/acme/access/grants", [
    "grantr:grant",
    "grantr:revoke",
    "grantr:add_member",
    "grantr:manage_groups",
  ]);
  await expect.element(screen.getByRole("combobox", { name: "Role" })).toBeVisible();
  expect(await optionsOf(screen, "Role")).toEqual(["Choose a role…", "editor", "viewer"]);
  await expect
    .element(screen.getByRole("button", { name: /^Revoke alice \(person\) as owner/ }))
    .not.toBeInTheDocument();
  await expect
    .element(screen.getByRole("button", { name: /^Revoke bob \(person\) as editor/ }))
    .toBeVisible();
});

test("without revoking, Grants has no Revoke", async () => {
  const { screen } = await open("/t/acme/access/grants", ["grantr:grant"]);
  await expect.element(screen.getByRole("table", { name: "Workspace ws_1" })).toBeVisible();
  await expect.element(screen.getByRole("button", { name: /^Revoke/ })).not.toBeInTheDocument();
});

test("revoking a grant is confirmed, and sends the grant", async () => {
  const { screen } = await open("/t/acme/access/grants", TENANT_ACTIONS);
  const revoke = screen.getByRole("button", {
    name: "Revoke ops (group) as viewer on thread t_1 in ws_1",
  });
  // A row's action shows "Revoke", and says what it revokes only aloud.
  await expect.element(revoke).toBeVisible();
  expect(revoke.element().firstChild?.textContent).toBe("Revoke");
  expect(revoke.element().querySelector(".sr-only")).not.toBeNull();
  await revoke.click();
  await screen.getByRole("alertdialog").getByRole("button", { name: "Revoke" }).click();
  await expect.element(screen.getByRole("alertdialog")).not.toBeInTheDocument();
  expect(sent).toEqual([
    {
      to: "POST /grantr/v1/tenants/acme/revocations",
      body: JSON.stringify({
        role: "viewer",
        on: { kind: "thread", workspace: "ws_1", id: "t_1" },
        to: { kind: "group", id: "ops" },
      }),
    },
  ]);
});

test("a refused revocation keeps the dialog open, and says why", async () => {
  const { screen } = await open("/t/acme/access/grants", TENANT_ACTIONS);
  await screen
    .getByRole("button", { name: "Revoke bob (person) as editor on workspace ws_1" })
    .click();
  const dialog = screen.getByRole("alertdialog");
  await dialog.getByRole("button", { name: "Revoke" }).click();
  await expect
    .element(dialog.getByRole("alert"))
    .toHaveTextContent("Not revoked: holds less than editor gives: reflexr:retry_run");
});
