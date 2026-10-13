/**
 * Access as a route, over a stubbed grantr: what each part shows for what grantr allows, the
 * part not allowed said in the tenant's frame, and a key's secret gone once its screen is left.
 */

import {
  type Config,
  createApi,
  createCommands,
  createQueries,
  createQueryClient,
  Signed,
} from "@portalr/client";
import { QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, createRouter, RouterProvider } from "@tanstack/react-router";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { page } from "vitest/browser";
import { render } from "vitest-browser-react";
import { ACCESS } from "./access";
import { routeTree } from "./routeTree.gen";

const CONFIG: Config = {
  supabase: { url: "http://127.0.0.1:9", key: "sb_publishable_x" },
  surfaces: { artifactr: "/artifactr/v1", reflexr: "/reflexr/v1", grantr: "", portalr: "" },
  readers: { tempo: false },
};

/** alice, signed in, as Supabase Auth would say, without asking it. */
class Alice extends Signed {
  override signedIn = async () => "alice";
  override email = () => "alice@example.com";
}

/** Each change Access sent: its method and path, and its body. */
const sent: { readonly to: string; readonly body: unknown }[] = [];
const keyring = [{ id: "k_1", principal: { kind: "service_principal", id: "ci" } }];

/** grantr, as far as Access reads it: alice owns acme, and grantr allows `allowed` there. */
function grantr(allowed: readonly string[]) {
  return async (input: RequestInfo | URL, init?: RequestInit) => {
    const request = new Request(input, init);
    const path = new URL(request.url).pathname;
    if (request.method === "PUT" || request.method === "DELETE") {
      sent.push({ to: `${request.method} ${path}`, body: await request.text() });
      return Response.json({ at: "2026-10-13T00:00:00Z", by: null, seq: 2, tenant: "acme" });
    }
    if (path === "/grantr/v1/me") {
      return Response.json({ memberships: [{ tenant: "acme", user: "alice", roles: ["owner"] }] });
    }
    if (path === "/grantr/v1/checks") {
      const asked: { action: string }[] = await request.json();
      return Response.json(asked.map(({ action }) => allowed.includes(action)));
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
    return Response.json({ detail: "not here" }, { status: 403 });
  };
}

async function open(path: string, allowed: readonly string[]) {
  vi.stubGlobal("fetch", vi.fn(grantr(allowed)));
  const signed = new Alice(CONFIG, () => undefined);
  const queryClient = createQueryClient(() => undefined);
  const api = createApi(CONFIG.surfaces, () => ({ token: "t0k3n" }));
  const router = createRouter({
    routeTree,
    history: createMemoryHistory({ initialEntries: [path] }),
    context: {
      config: CONFIG,
      signed,
      queries: createQueries(api),
      commands: createCommands(api, () => undefined),
      queryClient,
    },
  });
  const screen = await render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return { screen, router };
}

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
  const { screen } = await open("/t/acme/access/members", ACCESS);
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
  const { screen, router } = await open("/t/acme/access/keys", ACCESS);
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
  const { screen } = await open("/t/acme/access/keys", ACCESS);
  await screen.getByRole("button", { name: "Issue" }).click();
  await expect.element(screen.getByRole("textbox", { name: "The key" })).toBeVisible();
  await screen.getByRole("button", { name: "Done" }).click();
  await expect.element(screen.getByRole("textbox", { name: "The key" })).not.toBeInTheDocument();
});

test("Create refuses a group's name that is taken, rather than replace its members", async () => {
  const { screen } = await open("/t/acme/access/groups", ACCESS);
  await screen.getByRole("textbox", { name: "Group" }).fill("ops");
  await screen.getByRole("button", { name: "Create the group" }).click();
  await expect
    .element(screen.getByRole("alert"))
    .toHaveTextContent("Not saved: ops is a group already. Change its members from its row.");
  expect(sent).toEqual([]);
});

test("Change members starts from the group's members, and confirms whom it takes out", async () => {
  const { screen } = await open("/t/acme/access/groups", ACCESS);
  await expect.element(screen.getByRole("cell", { name: "bob (person)" })).toBeVisible();
  await screen.getByRole("button", { name: "Change members" }).click();
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
  const { screen } = await open("/t/acme/access/keys", ACCESS);
  await screen.getByRole("button", { name: "Issue" }).click();
  await expect.element(screen.getByRole("textbox", { name: "The key" })).toBeVisible();
  await screen.getByRole("button", { name: "Revoke k_2" }).click();
  await screen.getByRole("alertdialog").getByRole("button", { name: "Revoke" }).click();
  await expect.element(screen.getByRole("textbox", { name: "The key" })).not.toBeInTheDocument();
});
