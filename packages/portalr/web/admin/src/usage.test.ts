import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "vitest";
import {
  askedOf,
  blocksOf,
  durationSaid,
  LEVELS,
  levelOf,
  MOST_WORKSPACES,
  partsOf,
  shownOf,
  trackerLabel,
} from "./usage";

const PORTALR_SCHEMA = join(import.meta.dirname, "../../../schemas/portalr.openapi.json");

const usage = {
  days: [
    { day: "2026-10-11", spend: 0, tokens: 0, requests: 0 },
    { day: "2026-10-12", spend: 2, tokens: 200, requests: 4 },
    { day: "2026-10-13", spend: 4, tokens: 400, requests: 8 },
  ],
  workspaces: [
    { workspace: "plans", spend: 3, tokens: 300 },
    { workspace: "notes", spend: 1, tokens: 100 },
  ],
  budget: { spend: 6, max_budget: 90, budget_duration: "30d" },
  daily_budget: 3,
  complete: true,
};

test("a budget's duration is read in words", () => {
  expect(durationSaid("30d")).toBe("over 30 days");
  expect(durationSaid("1mo")).toBe("over 1 month");
  expect(durationSaid("2w")).toBe("over 2 weeks");
  expect(durationSaid(" Monthly ")).toBe("a month");
  expect(durationSaid("hourly")).toBe("an hour");
  expect(durationSaid("soon")).toBe("per soon");
  expect(trackerLabel(3, { spend: 6, max_budget: 90, budget_duration: "30d" })).toBe(
    "Each day's spend against its share of the budget: $3.00 a day, of $90.00 over 30 days",
  );
  expect(trackerLabel(3, { spend: 6, max_budget: null, budget_duration: null })).toBe(
    "Each day's spend against its share of the budget: $3.00 a day",
  );
});

test("the most workspaces is what the schema allows", () => {
  const schema = JSON.parse(readFileSync(PORTALR_SCHEMA, "utf8"));
  const parameters: { name: string; schema: { maxItems: number } }[] =
    schema.paths["/portalr/v1/usage"].get.parameters;
  expect(parameters.find((one) => one.name === "workspaces")?.schema.maxItems).toBe(
    MOST_WORKSPACES,
  );
});

test("the address keeps a window Usage offers", () => {
  expect(shownOf({})).toEqual({ days: 7 });
  expect(shownOf({ days: "30" })).toEqual({ days: 30 });
});

test("a read asks after the tenant's workspaces, in order, fifty at most", () => {
  expect(askedOf(["plans", "notes"])).toEqual(["notes", "plans"]);
  const many = Array.from({ length: 60 }, (_, at) => `w${String(at).padStart(2, "0")}`);
  expect(askedOf(many)).toHaveLength(MOST_WORKSPACES);
});

test("a day's spend is nothing, under, near or over its share", () => {
  expect([0, 1, 2.5, 3, 3.01].map((spend) => LEVELS[levelOf(spend, 3)]?.key)).toEqual([
    "none",
    "under",
    "near",
    "near",
    "over",
  ]);
  expect(blocksOf(usage, 3)).toEqual([
    { key: "2026-10-11", name: "2026-10-11", level: 0, figure: "$0.00" },
    { key: "2026-10-12", name: "2026-10-12", level: 1, figure: "$2.00" },
    { key: "2026-10-13", name: "2026-10-13", level: 3, figure: "$4.00" },
  ]);
  // A day a partial read never reached isn't in the answer, so it is no block.
  const partial = { ...usage, complete: false, days: usage.days.slice(1) };
  expect(blocksOf(partial, 3).map((block) => block.key)).toEqual(["2026-10-12", "2026-10-13"]);
});

test("what no workspace's tag holds is a part of its own, if a cent or more", () => {
  expect(partsOf(usage)).toEqual([
    { key: "plans", name: "plans", value: 3 },
    { key: "notes", name: "notes", value: 1 },
    { key: "~untagged", name: "No workspace", value: 2 },
  ]);
  const tagged = {
    ...usage,
    workspaces: [{ workspace: "notes", spend: 6.001, tokens: 1 }],
  };
  expect(partsOf(tagged)).toEqual([{ key: "notes", name: "notes", value: 6.001 }]);
  // Where a read stopped short, the two totals cover different days: no part is made of the rest.
  expect(partsOf({ ...usage, complete: false }).map((part) => part.key)).toEqual([
    "plans",
    "notes",
  ]);
});
