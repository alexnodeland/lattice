/**
 * A `rule` artifact reads as its pipeline (portalr ADR-0017): in its thread, with what its preview
 * found; on its page; and an edit's proposal says what it changes, stage by stage.
 */

import { afterEach, expect, test, vi } from "vitest";
import { applyPatch } from "./json-patch";
import { RENDERERS } from "./renderers";
import { open } from "./test/app";
import { FIRED, serve, WORLD } from "./test/rules";

afterEach(() => vi.unstubAllGlobals());

test("rule is a kind the app draws, shown inline in its thread", () => {
  expect(RENDERERS.get("rule")?.inline).toBe(true);
});

test("in its thread, a rule is its pipeline, with what its preview found, and an edit says what it changes", async () => {
  const { screen } = await open("/t/acme/w/notes/threads/thr_r", serve, () => null, WORLD);
  const card = screen.getByRole("listitem", { name: "ops.page_on_severe_tickets" });
  await expect.element(card.getByText(FIRED, { exact: true })).toBeVisible();
  await expect
    .element(card.getByText("fires when 3 arrive within 10 minutes, then starts over").first())
    .toBeVisible();
  await expect.element(card.getByText("severity ≥ 7").first()).toBeVisible();
  const edit = screen.getByRole("region", { name: "Proposal: Edit the rule" });
  const throttle = edit.getByRole("region", { name: "throttle" });
  await expect.element(throttle).toBeVisible();
  expect(throttle.element().textContent).toContain("removed: 15");
  expect(throttle.element().textContent).toContain("added: 5");
  const filter = edit.getByRole("region", { name: "filter" });
  // The filter added is the one line added: the rest is as it was.
  expect(filter.element().textContent).toContain('added: and env = "prod"');
  expect(filter.element().textContent).not.toContain("removed");
  expect(edit.getByRole("region", { name: "action" }).query()).toBeNull();
});

test("on its page, a rule is its pipeline, its JSON a fold away, and its revisions compare it stage by stage", async () => {
  const { screen } = await open("/t/acme/w/notes/artifacts/rule_1", serve, () => null, WORLD);
  await expect.element(screen.getByText(FIRED, { exact: true })).toBeVisible();
  await expect
    .element(screen.getByRole("list", { name: "The rule, stage by stage" }).first())
    .toBeVisible();
  await expect.element(screen.getByText("per service").first()).toBeVisible();
  await expect.element(screen.getByRole("button", { name: "The rule, as JSON" })).toBeVisible();
  // Its revisions say which stage changed, and open on what it was and what it is.
  const second = screen.getByRole("listitem", { name: "Version 2" });
  await expect.element(second.getByText("Changed the throttle")).toBeVisible();
  await second.getByRole("button", { name: /Version 2/ }).click();
  const throttle = second.getByRole("region", { name: "throttle" });
  expect(throttle.element().textContent).toContain("removed: 1");
  expect(throttle.element().textContent).toContain("added: 2");
  expect(second.getByRole("region", { name: "filter" }).query()).toBeNull();
});

test("a patch applies as artifactr applies it, and one that doesn't gives nothing", () => {
  const data = { rule: { a: [1, 2], b: { "x/y": 1, "t~": 2 } } };
  expect(
    applyPatch(data, [
      { op: "add", path: "/rule/a/-", value: 3 },
      { op: "add", path: "/rule/a/0", value: 0 },
      { op: "replace", path: "/rule/b/x~1y", value: 5 },
      { op: "move", from: "/rule/b/t~0", path: "/rule/c" },
      { op: "remove", path: "/rule/a/1" },
    ]),
  ).toEqual({ rule: { a: [0, 2, 3], b: { "x/y": 5 }, c: 2 } });
  expect(data).toEqual({ rule: { a: [1, 2], b: { "x/y": 1, "t~": 2 } } });
  expect(applyPatch(data, [{ op: "remove", path: "/rule/zz" }])).toBeNull();
  expect(applyPatch(data, [{ op: "test", path: "/rule/a", value: [] }])).toBeNull();
  expect(applyPatch(data, [{ op: "move", path: "/x" }])).toBeNull();
  expect(applyPatch(data, [{ op: "add", path: "/rule/a/9", value: 1 }])).toBeNull();
  expect(applyPatch(data, [{ op: "add", path: "/no/such", value: 1 }])).toBeNull();
  expect(applyPatch(data, [{ op: "frobnicate", path: "/x" }])).toBeNull();
  expect(applyPatch(data, [{ op: "add", path: "", value: 1 }])).toBeNull();
  // An array's index is digits alone: not `length`, nor `1.0`, `1e0` or ` 1`.
  for (const index of ["length", "1.0", "1e0", " 1", "01", "-1"]) {
    expect(applyPatch(data, [{ op: "remove", path: `/rule/a/${index}` }]), index).toBeNull();
  }
  // Nothing reaches a prototype.
  for (const key of ["__proto__", "constructor", "prototype"]) {
    expect(
      applyPatch(data, [{ op: "add", path: `/rule/${key}`, value: { polluted: 1 } }]),
    ).toBeNull();
    expect(applyPatch(data, [{ op: "add", path: `/${key}/x`, value: 1 }])).toBeNull();
  }
  expect(({} as Record<string, unknown>).polluted).toBeUndefined();
  // An add or a replace without a value, and ops that aren't a list of ops, don't apply.
  expect(applyPatch(data, [{ op: "add", path: "/rule/z" }])).toBeNull();
  expect(applyPatch(data, [{ op: "replace", path: "/rule/a" }])).toBeNull();
  expect(applyPatch(data, [null])).toBeNull();
  expect(applyPatch(data, "ops")).toBeNull();
  expect(applyPatch(null, [])).toBeNull();
});

test("a drift proposed back from reflexr, on the Proposals page, names the stage it changes", async () => {
  const { screen } = await open("/t/acme/w/notes/proposals", serve, () => null, WORLD);
  const drift = screen.getByRole("region", {
    name: "Proposal: Bring the rule in line with reflexr",
  });
  const scope = drift.getByRole("region", { name: "scope" });
  await expect.element(scope).toBeVisible();
  expect(scope.element().textContent).toContain("removed: service");
  expect(scope.element().textContent).toContain("added: team");
  expect(drift.getByRole("region", { name: "throttle" }).query()).toBeNull();
  await expect.element(drift.getByText("Compared with version 2, the latest.")).toBeVisible();
});

test("an edit whose patch can't apply says so, against which version, with its changes as sent", async () => {
  const { screen } = await open("/t/acme/w/notes/proposals", serve, () => null, WORLD);
  const bad = screen.getByRole("region", { name: "Proposal: A patch that can't apply" });
  await expect
    .element(bad.getByText("Couldn't work out what this changes in version 1.", { exact: false }))
    .toBeVisible();
  await expect.element(bad.getByText("json_patch", { exact: false })).toBeVisible();
  expect(bad.element().textContent).toContain("/rule/scope/fields/length");
});
