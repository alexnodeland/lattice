/**
 * Settings as a route, over a stubbed grantr that keeps rows and decides as grantr does (lattice
 * ADR-0030): on the rail where grantr allows narrowing them, the heading taking the focus, the
 * tenant or a workspace chosen in the address, what applies and the ceiling with who set it, a
 * value lowered at the version read and said, a raise refused in grantr's words on the field, a
 * change someone made first said and focused, clamped rows and unknown keys said.
 */

import { choose } from "@portalr/ui/testing";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { page, userEvent } from "vitest/browser";
import { open as opened } from "./test/admin";

type Row = { value: number | null; version: number; by: { kind: "user"; id: string }; at: string };

const KEY = "connect-per-hour:freecad";
const DESCRIPTION =
  "How many tries at code and network calls to a connected FreeCAD a workspace may make an hour.";
const OPERATOR = 60;

/** The rows grantr keeps: the tenant's under "", each workspace's under its name. */
const rows = new Map<string, Row>();
/** Each change sent: its level, If-Match and body. */
const sent: string[] = [];
/** Keys stored no registry declares any more, as grantr lists them. */
let unknown: string[] = [];
/** A version someone else moved the tenant's row to before the next change lands. */
let racing = false;
/** What a change waits for before it is answered, so a test can act while it is under way. */
let held: Promise<void> | null = null;
/** Someone else saves the same value again before the next change lands: a new version only. */
let sameValueRace = false;
/** Whether grantr lists a setting of names too. */
let names = false;
/** Whether the tenant has 120 workspaces, past the 99 one read of grantr's checks asks about. */
let many = false;
const WORKSPACES = ["notes", "plans"];

/** The tools the tenant leaves a workspace: create_object isn't among them. */
const OFFERED = ["get_objects", "get_view"];

/** What a workspace has set of its tools, if anything, by name. */
const tools = new Map<string, { value: string[] | null; version: number }>();

/** Whether grantr refuses the next change of the tools, and whether someone changes them first. */
let refusingTools = false;
let racingTools = false;

/** A setting of names, as grantr lists it at a workspace: the tenant's ceiling, and what is set. */
function toolsOf(workspace: string | null) {
  const here = tools.get(workspace ?? "") ?? null;
  const value = here?.value ?? null;
  const kept = value === null ? OFFERED : value.filter((name) => OFFERED.includes(name));
  return {
    key: "connect-tools:freecad",
    description:
      "Which of a connected FreeCAD's tools a workspace offers, of those its operator offers.",
    kind: {
      type: "subset",
      low: null,
      high: null,
      universe: ["create_object", "get_objects", "get_view", "unlabelled"],
      labels: { create_object: "edits", get_objects: "reads", get_view: "reads" },
    },
    default: ["create_object", "get_objects", "get_view", "unlabelled"],
    lowest: "workspace",
    operator: null,
    tenant: null,
    workspace:
      value === null
        ? null
        : {
            value,
            version: here?.version ?? 0,
            by: { kind: "user", id: "alice" },
            at,
            clamped: kept.length !== value.length,
          },
    version: here?.version ?? 0,
    ceiling: OFFERED,
    ceiling_set_by: "tenant",
    effective: kept,
  };
}

const at = "2026-10-22T09:00:00Z";

/** A setting's state at a level, decided as grantr does: each layer narrows the one above. */
function stateOf(workspace: string | null) {
  const tenant = rows.get("") ?? null;
  const here = workspace === null ? null : (rows.get(workspace) ?? null);
  const onTenant = Math.min(OPERATOR, tenant?.value ?? OPERATOR);
  const effective = Math.min(onTenant, here?.value ?? onTenant);
  const layer = (row: Row | null, above: number) =>
    row && row.value !== null
      ? {
          value: row.value,
          version: row.version,
          by: row.by,
          at: row.at,
          clamped: row.value > above,
        }
      : null;
  const mine = workspace === null ? tenant : here;
  return {
    key: KEY,
    description: DESCRIPTION,
    kind: { type: "int_range", low: 0, high: 1000, universe: null },
    default: 30,
    lowest: "workspace",
    operator: OPERATOR,
    tenant: layer(tenant, OPERATOR),
    workspace: workspace === null ? null : layer(here, onTenant),
    version: mine?.version ?? 0,
    ceiling: workspace === null ? OPERATOR : onTenant,
    ceiling_set_by: workspace !== null && tenant?.value != null ? "tenant" : "operator",
    effective: workspace === null ? onTenant : effective,
  };
}

/** grantr's settings, and artifactr's list of workspaces, past what the harness answers. */
async function grantr(request: Request, path: string): Promise<Response | undefined> {
  if (path === "/artifactr/v1/workspaces") {
    return Response.json(many ? Array.from({ length: 120 }, (_, n) => `w${n + 100}`) : WORKSPACES);
  }
  if (path === "/portalr/v1/people") {
    return Response.json({ people: { alice: "alice@acme.test" } });
  }
  const match = /^\/grantr\/v1\/tenants\/acme(?:\/workspaces\/([^/]+))?\/settings(?:\/(.+))?$/.exec(
    decodeURIComponent(path),
  );
  if (!match) {
    return undefined;
  }
  const [, workspace = null, key] = match;
  if (request.method === "PUT" && key) {
    const body = await request.text();
    const tag = request.headers.get("If-Match");
    sent.push(`${workspace ?? "tenant"} ${tag} ${body}`);
    await held;
    if (key === "connect-tools:freecad") {
      const name = workspace ?? "";
      if (racingTools) {
        racingTools = false;
        tools.set(name, { value: ["get_objects"], version: 5 });
      }
      const stored = tools.get(name);
      if (tag !== `"${stored?.version ?? 0}"`) {
        const message = `connect-tools:freecad is at version ${stored?.version ?? 0} here`;
        return Response.json({ detail: { type: "version_conflict", message } }, { status: 409 });
      }
      if (refusingTools) {
        const message = "connect-tools:freecad may be at most get_objects, get_view here";
        return Response.json({ detail: { type: "invalid", message } }, { status: 422 });
      }
      const { value } = JSON.parse(body) as { value: string[] | null };
      tools.set(name, { value, version: (stored?.version ?? 0) + 1 });
      return Response.json(toolsOf(workspace));
    }
    const name = workspace ?? "";
    if (sameValueRace) {
      sameValueRace = false;
      const before = rows.get(name);
      if (before) {
        rows.set(name, { ...before, version: before.version + 4 });
      }
    }
    if (racing) {
      racing = false;
      rows.set(name, { value: 7, version: 5, by: { kind: "user", id: "alice" }, at });
    }
    const stored = rows.get(name);
    if (tag !== `"${stored?.version ?? 0}"`) {
      const message = `${KEY} is at version ${stored?.version ?? 0} here, not ${tag}`;
      return Response.json({ detail: { type: "version_conflict", message } }, { status: 409 });
    }
    const { value } = JSON.parse(body) as { value: number | null };
    const ceiling = stateOf(workspace).ceiling;
    if (value !== null && value > ceiling) {
      const setter = workspace === null ? "operator" : "tenant";
      const message = `${KEY} may be at most ${ceiling} here: the ${setter}'s value`;
      return Response.json({ detail: { type: "invalid", message } }, { status: 422 });
    }
    rows.set(name, {
      value,
      version: (stored?.version ?? 0) + 1,
      by: { kind: "user", id: "alice" },
      at,
    });
    return Response.json(stateOf(workspace));
  }
  const listed = names ? [stateOf(workspace), toolsOf(workspace)] : [stateOf(workspace)];
  return Response.json({ settings: listed, unknown });
}

const open = (path: string, allowed: readonly string[] = ["grantr:manage_settings"]) =>
  opened(path, allowed, grantr);

beforeEach(async () => {
  await page.viewport(1280, 900);
});

afterEach(() => {
  rows.clear();
  sent.length = 0;
  unknown = [];
  racing = false;
  held = null;
  sameValueRace = false;
  names = false;
  many = false;
  tools.clear();
  refusingTools = false;
  racingTools = false;
  vi.unstubAllGlobals();
});

test("Settings is on the rail where grantr allows narrowing them, and its heading takes the focus", async () => {
  const { screen, router } = await open("/t/acme");
  const rail = screen.getByRole("navigation", { name: "Tenant" });
  await rail.getByRole("link", { name: "Settings" }).click();
  const heading = screen.getByRole("heading", { level: 1, name: "Settings" });
  await expect.element(heading).toHaveFocus();
  expect(router.state.location.pathname).toBe("/t/acme/settings");
});

test("where grantr doesn't allow narrowing them, they're not on the rail, nor found", async () => {
  const { screen } = await open("/t/acme/settings", ["grantr:read_audit"]);
  await expect.element(screen.getByText("Settings aren't yours to change here")).toBeVisible();
  const rail = screen.getByRole("navigation", { name: "Tenant" });
  await expect.element(rail.getByRole("link", { name: "Settings" })).not.toBeInTheDocument();
});

test("each setting is named by what it limits, with what applies, its ceiling and who set it", async () => {
  const { screen } = await open("/t/acme/settings");
  const field = screen.getByRole("textbox", { name: "FreeCAD's tries an hour" });
  await expect.element(field).toHaveValue("");
  await expect
    .element(screen.getByText("Applies: 60. At most 60: the operator's value."))
    .toBeVisible();
  await expect.element(screen.getByText(DESCRIPTION)).toBeVisible();
  expect(screen.getByText(KEY).elements()).toHaveLength(0);
});

test("a value is lowered at the version read, said, and the focus stays where it was", async () => {
  const { screen } = await open("/t/acme/settings?workspace=notes");
  const field = screen.getByRole("textbox", { name: "FreeCAD's tries an hour" });
  // The status is there, empty, before anything is said, so what is said is announced.
  await expect.element(field).toBeVisible();
  const quiet = screen
    .getByRole("status")
    .elements()
    .filter((one) => one.textContent === "");
  expect(quiet.length).toBeGreaterThan(0);
  await field.fill("12");
  await userEvent.keyboard("{Enter}");
  await expect.element(screen.getByText("FreeCAD's tries an hour: 12 applies.")).toBeVisible();
  await expect.element(screen.getByText(/^Set here to 12 by alice@acme\.test/)).toBeVisible();
  await expect.element(field).toHaveFocus();
  expect(sent).toEqual(['notes "0" {"value":12}']);
  const save = screen.getByRole("button", { name: "Save FreeCAD's tries an hour" });
  await field.fill("11");
  await save.click();
  await expect.element(screen.getByText(/^Set here to 11 by/)).toBeVisible();
  await expect.element(save).toHaveFocus();
  await screen
    .getByRole("button", { name: "Use the tenant's for FreeCAD's tries an hour" })
    .click();
  await expect
    .element(screen.getByText("Applies: 60. At most 60: the operator's value."))
    .toBeVisible();
  await expect.element(field).toHaveFocus();
  await expect.element(field).toHaveValue("");
  expect(sent).toEqual([
    'notes "0" {"value":12}',
    'notes "1" {"value":11}',
    'notes "2" {"value":null}',
  ]);
});

test("a value sent again while it is under way is sent once", async () => {
  let answer = () => {};
  held = new Promise((resolve) => {
    answer = resolve;
  });
  const { screen } = await open("/t/acme/settings");
  const field = screen.getByRole("textbox", { name: "FreeCAD's tries an hour" });
  await field.fill("12");
  (field.element() as HTMLElement).focus();
  await userEvent.keyboard("{Enter}");
  await expect.poll(() => sent.length).toBe(1);
  await userEvent.keyboard("{Enter}{Enter}");
  const save = screen.getByRole("button", { name: "Save FreeCAD's tries an hour" });
  await expect.element(save).toHaveAttribute("aria-disabled", "true");
  answer();
  await expect.element(screen.getByText("FreeCAD's tries an hour: 12 applies.")).toBeVisible();
  expect(sent).toEqual(['tenant "0" {"value":12}']);
  expect(screen.getByText(/changed by someone else/).elements()).toHaveLength(0);
});

test("a raise is refused on the field, in grantr's words, naming the ceiling and who set it", async () => {
  rows.set("", { value: 20, version: 1, by: { kind: "user", id: "alice" }, at });
  const { screen } = await open("/t/acme/settings?workspace=notes");
  await expect
    .element(screen.getByText("Applies: 20. At most 20: the tenant's value."))
    .toBeVisible();
  const field = screen.getByRole("textbox", { name: "FreeCAD's tries an hour" });
  await field.fill("25");
  await screen.getByRole("button", { name: "Save FreeCAD's tries an hour" }).click();
  await expect
    .element(field)
    .toHaveAccessibleDescription(
      /FreeCAD's tries an hour wasn't changed: FreeCAD's tries an hour may be at most 20 here: the tenant's value/,
    );
  await expect.element(field).toHaveFocus();
  expect(screen.getByText(/connect-per-hour:freecad/).elements()).toHaveLength(0);
  await field.fill("lots");
  await screen.getByRole("button", { name: "Save FreeCAD's tries an hour" }).click();
  await expect.element(field).toHaveAccessibleDescription(/Enter a whole number from 0 to 1000\./);
  expect(sent).toHaveLength(1);
});

test("a change someone made first is said, focused, and the setting shown as it is now", async () => {
  racing = true;
  const { screen } = await open("/t/acme/settings");
  await screen.getByRole("textbox", { name: "FreeCAD's tries an hour" }).fill("9");
  await screen.getByRole("button", { name: "Save FreeCAD's tries an hour" }).click();
  const told = screen.getByText(/was changed by someone else since you read it/);
  await expect.element(told).toBeVisible();
  await expect
    .poll(() => told.element().textContent)
    .toContain("it is set here to 7 now, and 7 applies. You tried to set 9, which wasn't saved");
  await expect.element(screen.getByText(/^Set here to 7 by alice/)).toBeVisible();
  await expect
    .element(screen.getByRole("textbox", { name: "FreeCAD's tries an hour" }))
    .toHaveValue("9");
  await expect
    .poll(() => document.activeElement?.textContent ?? "")
    .toContain("was changed by someone else");
});

test("a value the operator has since lowered below is said not to apply, and unknown keys are listed", async () => {
  rows.set("", { value: 90, version: 2, by: { kind: "user", id: "alice" }, at });
  unknown = ["connect-per-hour:retired"];
  const { screen } = await open("/t/acme/settings");
  await expect
    .element(
      screen.getByText("What is set here doesn't apply: 60 does, as no more is allowed now."),
    )
    .toBeVisible();
  await expect
    .element(screen.getByText(/no longer a setting, so never applied: connect-per-hour:retired/))
    .toBeVisible();
});

test("the level is chosen in the address", async () => {
  const { screen, router } = await open("/t/acme/settings");
  await choose(screen, "Where", "Workspace plans");
  await expect.element(screen.getByRole("list", { name: "Settings in plans" })).toBeVisible();
  expect(router.state.location.search).toEqual({ workspace: "plans" });
});

test("two submits in one tick send once", async () => {
  let answer = () => {};
  held = new Promise((resolve) => {
    answer = resolve;
  });
  const { screen } = await open("/t/acme/settings");
  await screen.getByRole("textbox", { name: "FreeCAD's tries an hour" }).fill("12");
  const form = (
    screen.getByRole("textbox", { name: "FreeCAD's tries an hour" }).element() as HTMLInputElement
  ).form;
  form?.requestSubmit();
  form?.requestSubmit();
  answer();
  await expect.element(screen.getByText("FreeCAD's tries an hour: 12 applies.")).toBeVisible();
  expect(sent).toEqual(['tenant "0" {"value":12}']);
});

test("a late answer doesn't take the focus from where the reader moved to", async () => {
  rows.set("", { value: 20, version: 1, by: { kind: "user", id: "alice" }, at });
  let answer = () => {};
  held = new Promise((resolve) => {
    answer = resolve;
  });
  const { screen } = await open("/t/acme/settings?workspace=notes");
  await screen.getByRole("textbox", { name: "FreeCAD's tries an hour" }).fill("25");
  await screen.getByRole("button", { name: "Save FreeCAD's tries an hour" }).click();
  const elsewhere = screen.getByRole("combobox", { name: "Where" });
  (elsewhere.element() as HTMLElement).focus();
  answer();
  await expect
    .element(screen.getByRole("textbox", { name: "FreeCAD's tries an hour" }))
    .toHaveAccessibleDescription(/may be at most 20 here/);
  await expect.element(elsewhere).toHaveFocus();
});

test("the same refusal twice takes the field's focus again", async () => {
  const { screen } = await open("/t/acme/settings");
  const field = screen.getByRole("textbox", { name: "FreeCAD's tries an hour" });
  const save = screen.getByRole("button", { name: "Save FreeCAD's tries an hour" });
  await field.fill("lots");
  await save.click();
  await expect.element(field).toHaveFocus();
  (save.element() as HTMLElement).focus();
  await userEvent.keyboard("{Enter}");
  await expect.element(field).toHaveFocus();
  expect(sent).toEqual([]);
});

test("an unset after someone else's change leaves the field empty", async () => {
  rows.set("", { value: 7, version: 1, by: { kind: "user", id: "alice" }, at });
  sameValueRace = true;
  const { screen } = await open("/t/acme/settings");
  const field = screen.getByRole("textbox", { name: "FreeCAD's tries an hour" });
  await field.fill("9");
  await screen.getByRole("button", { name: "Save FreeCAD's tries an hour" }).click();
  await expect.element(screen.getByText(/was changed by someone else/)).toBeVisible();
  await screen
    .getByRole("button", { name: "Use the operator's for FreeCAD's tries an hour" })
    .click();
  await expect.element(screen.getByText("FreeCAD's tries an hour: 60 applies.")).toBeVisible();
  await expect.element(field).toHaveValue("");
});

test("a workspace's tools are checked, each with its risk, and those the tenant leaves out can't be", async () => {
  names = true;
  const { screen } = await open("/t/acme/settings?workspace=notes");
  const group = screen.getByRole("group", { name: "FreeCAD's tools" });
  const view = group.getByRole("checkbox", { name: "get_view (reads)" });
  await expect.element(view).toBeChecked();
  const create = group.getByRole("checkbox", { name: "create_object (edits)" });
  await expect.element(create).toBeDisabled();
  await expect.element(create).toHaveAccessibleDescription("Not offered by the tenant");
  await expect.element(group.getByRole("checkbox", { name: "unlabelled" })).toBeDisabled();
  await view.click();
  const save = screen.getByRole("button", { name: "Save FreeCAD's tools" });
  await save.click();
  await expect.element(screen.getByText("FreeCAD's tools: get_objects applies.")).toBeVisible();
  await expect.element(save).toHaveFocus();
  expect(sent).toEqual(['notes "0" {"value":["get_objects"]}']);
  await screen.getByRole("button", { name: "Use the tenant's for FreeCAD's tools" }).click();
  await expect.element(group.getByRole("checkbox", { name: "get_objects (reads)" })).toHaveFocus();
  await expect.element(view).toBeChecked();
  expect(sent.at(-1)).toBe('notes "1" {"value":null}');
});

test("a tool set here that the tenant no longer offers isn't checked, and is left out on save", async () => {
  names = true;
  tools.set("notes", { value: ["create_object", "get_view"], version: 2 });
  const { screen } = await open("/t/acme/settings?workspace=notes");
  const group = screen.getByRole("group", { name: "FreeCAD's tools" });
  await expect
    .element(group.getByRole("checkbox", { name: "create_object (edits)" }))
    .not.toBeChecked();
  await expect.element(group.getByRole("checkbox", { name: "get_view (reads)" })).toBeChecked();
  await screen.getByRole("button", { name: "Save FreeCAD's tools" }).click();
  await expect.element(screen.getByText("FreeCAD's tools: get_view applies.")).toBeVisible();
  expect(sent).toEqual(['notes "2" {"value":["get_view"]}']);
});

test("a refused change of tools is said on the group, and its first box takes the focus", async () => {
  names = true;
  refusingTools = true;
  const { screen } = await open("/t/acme/settings?workspace=notes");
  await screen.getByRole("button", { name: "Save FreeCAD's tools" }).click();
  const group = screen.getByRole("group", { name: "FreeCAD's tools" });
  await expect
    .element(group)
    .toHaveAccessibleDescription(/FreeCAD's tools wasn't changed: FreeCAD's tools may be at most/);
  await expect.element(group.getByRole("checkbox", { name: "get_objects (reads)" })).toHaveFocus();
});

test("tools someone changed first are said, and what was tried stays checked", async () => {
  names = true;
  racingTools = true;
  const { screen } = await open("/t/acme/settings?workspace=notes");
  const group = screen.getByRole("group", { name: "FreeCAD's tools" });
  await group.getByRole("checkbox", { name: "get_objects (reads)" }).click();
  await screen.getByRole("button", { name: "Save FreeCAD's tools" }).click();
  await expect.element(screen.getByText(/was changed by someone else/)).toBeVisible();
  await expect
    .poll(() => screen.getByText(/was changed by someone else/).element().textContent)
    .toContain("You tried to set get_view, which wasn't saved");
  await expect
    .element(group.getByRole("checkbox", { name: "get_objects (reads)" }))
    .not.toBeChecked();
  await expect.element(group.getByRole("checkbox", { name: "get_view (reads)" })).toBeChecked();
});

test("a tenant's admin has every workspace, past the 99 a read asks about", async () => {
  many = true;
  const { screen } = await open("/t/acme/settings?workspace=w219");
  await expect.element(screen.getByRole("list", { name: "Settings in w219" })).toBeVisible();
});

test("a workspace's admin past the 99 is told where to change the rest", async () => {
  many = true;
  const { screen } = await open("/t/acme/settings", ["grantr:manage_settings@w100"]);
  await expect.element(screen.getByRole("list", { name: "Settings in w100" })).toBeVisible();
  await expect
    .element(screen.getByRole("combobox", { name: "Where" }))
    .toHaveAccessibleDescription(/Only the first 99 workspaces by name are checked here/);
});

test("a workspace the tenant doesn't have is said not to exist", async () => {
  const { screen } = await open("/t/acme/settings?workspace=nowhere");
  await expect.element(screen.getByText("No such workspace")).toBeVisible();
});

test("a workspace's admin finds Settings, and only the workspaces they administer", async () => {
  const { screen, router } = await open("/t/acme", ["grantr:manage_settings@plans"]);
  const rail = screen.getByRole("navigation", { name: "Tenant" });
  await rail.getByRole("link", { name: "Settings" }).click();
  await expect.element(screen.getByRole("list", { name: "Settings in plans" })).toBeVisible();
  expect(router.state.location.pathname).toBe("/t/acme/settings");
  await screen.getByRole("combobox", { name: "Where" }).click();
  // The list opens after the click resolves, a frame or more later: read once it has.
  const options = () =>
    screen
      .getByRole("option")
      .elements()
      .map((one) => one.textContent);
  await expect.poll(options).toEqual(["Workspace plans"]);
});

test("a workspace the reader doesn't administer isn't theirs to change", async () => {
  const { screen } = await open("/t/acme/settings?workspace=notes", [
    "grantr:manage_settings@plans",
  ]);
  await expect.element(screen.getByText("Not a workspace you administer")).toBeVisible();
});
