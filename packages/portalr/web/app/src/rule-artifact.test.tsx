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
  await expect.element(card.getByText("3 or more within 10 minutes").first()).toBeVisible();
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
      { op: "copy", from: "/rule/c", path: "/rule/d" },
      { op: "remove", path: "/rule/a/1" },
      { op: "test", path: "/rule/d", value: 2 },
    ]),
  ).toEqual({ rule: { a: [0, 2, 3], b: { "x/y": 5 }, c: 2, d: 2 } });
  expect(data).toEqual({ rule: { a: [1, 2], b: { "x/y": 1, "t~": 2 } } });
  expect(applyPatch(data, [{ op: "remove", path: "/rule/zz" }])).toBeNull();
  expect(applyPatch(data, [{ op: "test", path: "/rule/a", value: [] }])).toBeNull();
  expect(applyPatch(data, [{ op: "add", path: "/rule/a/9", value: 1 }])).toBeNull();
  expect(applyPatch(data, [{ op: "add", path: "/no/such", value: 1 }])).toBeNull();
  expect(applyPatch(data, [{ op: "copy", path: "/x" }])).toBeNull();
  expect(applyPatch(data, [{ op: "frobnicate", path: "/x" }])).toBeNull();
  expect(applyPatch(data, [{ op: "add", path: "", value: 1 }])).toBeNull();
});
