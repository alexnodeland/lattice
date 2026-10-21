/**
 * Runs as a route, over a stubbed grantr, relayr and reflexr stream: a rule's run links to the
 * tracker items its chain filed, and to those whose changes fired it (lattice RFC-0004), and with
 * no tracker, to none, without asking relayr.
 */

import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { page } from "vitest/browser";
import { open, type Serve } from "./test/app";

const ITEMS = "/relayr/v1/workspaces/notes/tracker/items";

const frame = (seq: number, event: Record<string, unknown>, chain = "c1") => ({
  type: "event",
  seq,
  id: `evt_${seq}`,
  ts: "2026-10-18T09:00:00Z",
  workspace_id: "notes",
  // A `tracker:` event is relayr's followers', which publish as the source `tracker`.
  actor: String(event.type).startsWith("tracker:")
    ? { kind: "source", name: "tracker" }
    : { kind: "system", name: "reflexr" },
  correlation_id: chain,
  event,
});

/** A person renamed OPS-7 in Plane, a rule fired on it, and its run filed OPS-12. */
const LOG = [
  frame(1, {
    type: "tracker:item_changed",
    tracker: "plane",
    project: "p",
    item_id: "i7",
    number: 7,
    name: "OPS-7",
    link: "https://plane.example/acme/browse/OPS-7/",
    key: null,
    field: "title",
    old: "before",
    new: "after",
  }),
  frame(2, {
    type: "reflexr:rule_fired",
    rule: "ops:follow-up",
    firing_id: "run_1",
    matched: [1],
    scope: {},
    scope_key: "",
  }),
  frame(3, { type: "reflexr:run_started", run_id: "run_1", rule: "ops:follow-up", attempt: 1 }),
  frame(4, { type: "reflexr:run_succeeded", run_id: "run_1", rule: "ops:follow-up" }),
];

const serve: Serve = async (request, path) => {
  if (path === "/grantr/v1/checks") {
    const asked: unknown[] = await request.json();
    return Response.json(asked.map(() => false));
  }
  if (path === ITEMS) {
    return Response.json({
      tracker: "plane",
      items: [
        {
          key: "follow-up/run_1",
          project: "p",
          id: "i12",
          number: 12,
          name: "OPS-12",
          link: "https://plane.example/acme/browse/OPS-12/",
          deleted: false,
          chains: ["c1"],
        },
      ],
    });
  }
  return undefined;
};

const run = (screen: Awaited<ReturnType<typeof open>>["screen"]) =>
  screen.getByRole("table", { name: "Rules' runs" }).getByRole("row", { name: "Run run_1" });

beforeEach(async () => {
  await page.viewport(1280, 900);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

test("a run links to the item that fired it, and to the one its chain filed", async () => {
  const { screen } = await open("/t/acme/w/notes/runs", serve, () => null, {
    reflexrLog: LOG,
    surfaces: { relayr: "" },
  });
  await expect
    .element(run(screen).getByRole("link", { name: "OPS-7, in Plane (opens in a new tab)" }))
    .toHaveAttribute("href", "https://plane.example/acme/browse/OPS-7/");
  await expect
    .element(run(screen).getByRole("link", { name: "OPS-12, in Plane (opens in a new tab)" }))
    .toHaveAttribute("href", "https://plane.example/acme/browse/OPS-12/");
  await expect.element(run(screen).getByText("From")).toBeVisible();
  await expect.element(run(screen).getByText("Filed as")).toBeVisible();
  // What the event said in the tracker isn't shown with the run.
  await expect.element(screen.getByText("after")).not.toBeInTheDocument();
});

test("with no tracker, relayr is never asked, and the run still links to what fired it", async () => {
  const { screen, fetched } = await open("/t/acme/w/notes/runs", serve, () => null, {
    reflexrLog: LOG,
  });
  await expect
    .element(run(screen).getByRole("link", { name: "OPS-7, in Plane (opens in a new tab)" }))
    .toBeVisible();
  await expect.element(screen.getByText("Filed as")).not.toBeInTheDocument();
  const asked = fetched.mock.calls.map(([input]) => new URL((input as Request).url).pathname);
  expect(asked.filter((path) => path.startsWith("/relayr/"))).toEqual([]);
});
