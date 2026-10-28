/**
 * Integrations as a route, over a stubbed grantr that keeps settings and decides as grantr does:
 * on the rail where grantr allows switching them, the tenant or a workspace chosen in the address,
 * each switch's state and where it comes from, a change sent once and said, the tenant's ceiling
 * and the deployment's, and a refusal said.
 */

import { choose } from "@portalr/ui/testing";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { page, userEvent } from "vitest/browser";
import { open as opened } from "./test/admin";

type Setting = { on: boolean; by: { kind: "user"; id: string }; at: string };

const REGISTRY = [
  { key: "ui:forms", default: true, description: "Forms: the agent asks with a form." },
  { key: "markdown:mermaid", default: false, description: "Mermaid: diagrams written as text." },
  { key: "excalidraw", default: false, description: "Diagrams: Excalidraw drawings." },
  { key: "tracker:plane", default: true, description: "Plane: work items in Plane." },
];
const INSTALLED = new Set(["ui:forms", "markdown:mermaid", "excalidraw"]);

/** The settings grantr keeps: the tenant's under "", each workspace's under its name. */
const settings = new Map<string, Map<string, Setting>>();
/** Each change sent: its method, path and body. */
const sent: string[] = [];
/** Whether grantr refuses the next change. */
let refusing = false;

const level = (workspace: string) => {
  const found = settings.get(workspace) ?? new Map<string, Setting>();
  settings.set(workspace, found);
  return found;
};

/** An integration's state at a level, decided as grantr does (grantr ADR-0034). */
function stateOf(key: string, workspace: string | null) {
  const known = REGISTRY.find((one) => one.key === key);
  if (!known) {
    throw new Error(key);
  }
  const tenant = level("").get(key) ?? null;
  const here = workspace === null ? null : (level(workspace).get(key) ?? null);
  const installed = INSTALLED.has(key);
  return {
    ...known,
    installed,
    tenant,
    workspace: here,
    enabled: installed && tenant?.on !== false && (here?.on ?? tenant?.on ?? known.default),
  };
}

/** grantr's integrations, and artifactr's list of workspaces, past what the harness answers. */
async function grantr(request: Request, path: string): Promise<Response | undefined> {
  if (path === "/artifactr/v1/workspaces") {
    return Response.json(["notes", "plans"]);
  }
  if (path === "/portalr/v1/people") {
    return Response.json({ people: { alice: "alice@acme.test" } });
  }
  const match =
    /^\/grantr\/v1\/tenants\/acme(?:\/workspaces\/([^/]+))?\/integrations(?:\/(.+))?$/.exec(
      decodeURIComponent(path),
    );
  if (!match) {
    return undefined;
  }
  const [, workspace = null, key] = match;
  if (request.method === "PUT" && key) {
    const body = await request.text();
    sent.push(`PUT ${workspace ?? "tenant"} ${key} ${body}`);
    if (refusing) {
      return Response.json(
        { detail: { type: "forbidden", message: "alice may not grantr:manage_integrations" } },
        { status: 403 },
      );
    }
    const { on } = JSON.parse(body) as { on: boolean | null };
    const at = level(workspace ?? "");
    if (on === null) {
      at.delete(key);
    } else {
      at.set(key, { on, by: { kind: "user", id: "alice" }, at: "2026-10-17T09:00:00Z" });
    }
    return Response.json(stateOf(key, workspace));
  }
  return Response.json(REGISTRY.map(({ key: one }) => stateOf(one, workspace)));
}

const open = (path: string, allowed: readonly string[] = ["grantr:manage_integrations"]) =>
  opened(path, allowed, grantr);

beforeEach(async () => {
  await page.viewport(1280, 900);
});

afterEach(() => {
  settings.clear();
  sent.length = 0;
  refusing = false;
  vi.unstubAllGlobals();
});

test("Integrations is on the rail where grantr allows switching them", async () => {
  const { screen, router } = await open("/t/acme");
  const rail = screen.getByRole("navigation", { name: "Tenant" });
  await rail.getByRole("link", { name: "Integrations" }).click();
  await expect.element(screen.getByRole("heading", { name: "Integrations" })).toBeVisible();
  expect(router.state.location.pathname).toBe("/t/acme/integrations");
});

test("where grantr doesn't allow switching them, they're not on the rail, nor found", async () => {
  const { screen } = await open("/t/acme/integrations", ["grantr:read_audit"]);
  await expect.element(screen.getByText("Integrations aren't yours to switch here")).toBeVisible();
  const rail = screen.getByRole("navigation", { name: "Tenant" });
  await expect.element(rail.getByRole("link", { name: "Audit" })).toBeVisible();
  await expect.element(rail.getByRole("link", { name: "Integrations" })).not.toBeInTheDocument();
});

test("on the tenant, each is on or off, by default or as set there, and the deployment's ceiling holds", async () => {
  const { screen } = await open("/t/acme/integrations");
  const table = screen.getByRole("table", { name: "Integrations on the tenant" });
  await expect.element(table.getByRole("switch", { name: "Forms" })).toBeChecked();
  await expect
    .element(table.getByRole("switch", { name: "Forms" }))
    .toHaveAccessibleDescription("On Default");
  await expect.element(table.getByRole("switch", { name: "Mermaid" })).not.toBeChecked();
  const plane = table.getByRole("switch", { name: "Plane" });
  await expect.element(plane).toBeDisabled();
  await expect.element(plane).toHaveAccessibleDescription(/^Off Not installed in this deployment/);
});

test("a switch turned with the keyboard is set once, said, and shows who set it", async () => {
  const { screen } = await open("/t/acme/integrations?workspace=notes");
  const mermaid = screen.getByRole("switch", { name: "Mermaid" });
  await expect.element(mermaid).not.toBeChecked();
  (mermaid.element() as HTMLElement).focus();
  await userEvent.keyboard(" ");
  await expect.element(screen.getByRole("status")).toHaveTextContent("Mermaid is on in notes.");
  await expect.element(mermaid).toBeChecked();
  await expect.element(mermaid).toHaveAccessibleDescription("On Set here");
  const row = screen.getByRole("row", { name: "Mermaid" });
  await expect.element(row.getByText("alice@acme.test (person)")).toBeVisible();
  expect(sent).toEqual(['PUT notes markdown:mermaid {"on":true}']);
});

test("a workspace inherits the tenant's setting, and goes back to it", async () => {
  level("").set("markdown:mermaid", {
    on: true,
    by: { kind: "user", id: "alice" },
    at: "2026-10-16T09:00:00Z",
  });
  level("plans").set("markdown:mermaid", {
    on: false,
    by: { kind: "user", id: "alice" },
    at: "2026-10-16T10:00:00Z",
  });
  const { screen } = await open("/t/acme/integrations?workspace=notes");
  await expect
    .element(screen.getByRole("switch", { name: "Mermaid" }))
    .toHaveAccessibleDescription("On Inherited from the tenant");
  await choose(screen, "Where", "Workspace plans");
  const mermaid = screen.getByRole("switch", { name: "Mermaid" });
  await expect.element(mermaid).toHaveAccessibleDescription("Off Set here");
  await screen.getByRole("button", { name: "Back to inherited for Mermaid" }).click();
  await expect
    .element(screen.getByRole("status"))
    .toHaveTextContent("Mermaid is back to the tenant's in plans: on.");
  await expect.element(mermaid).toHaveAccessibleDescription("On Inherited from the tenant");
  expect(sent).toEqual(['PUT plans markdown:mermaid {"on":null}']);
});

test("the tenant's off is a ceiling a workspace's switch can't lift", async () => {
  level("").set("excalidraw", {
    on: false,
    by: { kind: "user", id: "alice" },
    at: "2026-10-16T09:00:00Z",
  });
  const { screen } = await open("/t/acme/integrations?workspace=notes");
  const diagrams = screen.getByRole("switch", { name: "Diagrams" });
  await expect.element(diagrams).toBeDisabled();
  await expect
    .element(diagrams)
    .toHaveAccessibleDescription(
      "Off Off for the tenant The tenant turned it off, so no workspace can turn it on.",
    );
});

test("a change grantr refuses says why, and leaves the switch as it was", async () => {
  refusing = true;
  const { screen } = await open("/t/acme/integrations");
  const forms = screen.getByRole("switch", { name: "Forms" });
  await forms.click();
  await expect
    .element(screen.getByRole("alert"))
    .toHaveTextContent("Forms wasn't changed: you may not do this here.");
  await expect.element(forms).toBeChecked();
  await expect.element(forms).toBeEnabled();
});

test("who set one links to the audit log's switched integrations, where it may be read", async () => {
  level("").set("ui:forms", {
    on: false,
    by: { kind: "user", id: "alice" },
    at: "2026-10-16T09:00:00Z",
  });
  const { screen, router } = await open("/t/acme/integrations", [
    "grantr:manage_integrations",
    "grantr:read_audit",
  ]);
  await screen
    .getByRole("row", { name: "Forms" })
    .getByRole("link", { name: "See the audit log for Forms" })
    .click();
  await expect.poll(() => router.state.location.pathname).toBe("/t/acme/audit");
  expect(router.state.location.search).toEqual(
    expect.objectContaining({ type: "integration_set" }),
  );
});

test("a workspace the tenant doesn't have is said, and the tenant can be chosen", async () => {
  const { screen, router } = await open("/t/acme/integrations?workspace=gone");
  await expect.element(screen.getByText("No such workspace")).toBeVisible();
  await choose(screen, "Where", "The tenant");
  await expect
    .element(screen.getByRole("table", { name: "Integrations on the tenant" }))
    .toBeVisible();
  expect(router.state.location.search).toEqual({});
});

test("an integration that is on and brings an app has a way to open it, in a new tab; one off has none (portalr ADR-0088)", async () => {
  const links = {
    "ui:forms": "http://127.0.0.1:8090/",
    "markdown:mermaid": "http://127.0.0.1:8091/",
  };
  const { screen } = await opened(
    "/t/acme/integrations",
    ["grantr:manage_integrations"],
    grantr,
    ["acme"],
    { links },
  );
  const table = screen.getByRole("table", { name: "Integrations on the tenant" });
  const forms = table.getByRole("link", { name: "Open Forms (opens in a new tab)" });
  await expect.element(forms).toHaveAttribute("href", links["ui:forms"]);
  await expect.element(forms).toHaveAttribute("target", "_blank");
  await expect.element(forms).toHaveAttribute("rel", "noopener noreferrer");
  // Mermaid is off by default: no way to its app.
  expect(table.getByRole("link", { name: /Open Mermaid/ }).elements()).toHaveLength(0);
  // Turned on, it has one; turned off again, none.
  await table.getByRole("switch", { name: "Mermaid" }).click();
  await expect.element(table.getByRole("link", { name: /Open Mermaid/ })).toBeVisible();
  await table.getByRole("switch", { name: "Mermaid" }).click();
  await expect.element(table.getByRole("link", { name: /Open Mermaid/ })).not.toBeInTheDocument();
  // The keyboard reaches it after the switch.
  forms.element().focus();
  await expect.element(forms).toHaveFocus();
});
