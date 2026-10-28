/**
 * A rule as its pipeline (portalr ADR-0017): each stage in words, in reflexr's order; what isn't
 * known, as JSON in its place; and an edit compared stage by stage, read the same to a screen
 * reader as it looks.
 */

import type { Artifactr } from "@portalr/client";
import { expect, test } from "vitest";
import { render } from "vitest-browser-react";
import { ProposedChanges } from "./revisions";
import { FiredContext, firedOf, RulePipeline, rule } from "./rule";
import { duration, filterLine, stages, stageText } from "./rule-words";
import { axeViolations } from "./test/axe";
import { compare } from "./test/compare";

const on = { kind: "on", types: ["portal:ticket.opened"] };

const RULE = {
  name: "ops.page_on_fire",
  when: {
    filter: {
      kind: "all",
      of: [on, { kind: "where", field: "severity", op: "ge", value: 7 }],
    },
    pattern: { kind: "count", at_least: 3, within: "PT1M" },
    throttle: { at_most: 1, per: "PT15M" },
  },
  scope: { fields: ["service"] },
  // biome-ignore lint/suspicious/noThenProperty: a reflexr rule names its action `then`, as data, never awaited.
  then: { action: "page", params: { to: "oncall", urgent: true } },
  timeout: "PT30S",
};

/** What a stage says, as text. */
const said = (rule: Record<string, unknown>, name: string) =>
  stageText(stages(rule).find((stage) => stage.name === name)?.lines ?? []);

const withWhen = (when: Record<string, unknown>) => ({ ...RULE, when: { filter: on, ...when } });

test("a duration is in words; one it can't read, as written", () => {
  expect(duration("PT1M")).toBe("1 minute");
  expect(duration("PT15M")).toBe("15 minutes");
  expect(duration("PT1H30M")).toBe("1 hour and 30 minutes");
  expect(duration("P1DT2H5S")).toBe("1 day, 2 hours and 5 seconds");
  expect(duration("P2W")).toBe("2 weeks");
  expect(duration("PT0.5S")).toBe("0.5 seconds");
  expect(duration("soon")).toBe("soon");
  expect(duration("PT")).toBe("PT");
});

test("the stages come in reflexr's order, each always there", () => {
  expect(stages(RULE).map((stage) => stage.name)).toEqual([
    "event types",
    "filter",
    "pattern",
    "dedupe",
    "throttle",
    "scope",
    "action",
    "retries",
    "timeout",
    "runs",
  ]);
  expect(said(RULE, "event types")).toBe("portal:ticket.opened");
  expect(said(RULE, "filter")).toBe("severity ≥ 7");
  expect(said(RULE, "timeout")).toBe("30 seconds");
});

test.each([
  ["eq", "open", 'status = "open"'],
  ["ne", "open", 'status ≠ "open"'],
  ["lt", 3, "status < 3"],
  ["le", 3, "status ≤ 3"],
  ["gt", 3, "status > 3"],
  ["ge", 3, "status ≥ 3"],
  ["in", ["a", "b"], 'status is one of "a", "b"'],
  ["contains", "x", 'status contains "x"'],
  ["matches", "^P[12]$", 'status matches "^P[12]$"'],
  ["exists", null, "status exists"],
  ["exists", false, "status is missing"],
])("a where with %s is a sentence", (op, value, sentence) => {
  expect(filterLine({ kind: "where", field: "status", op, value }).said).toBe(sentence);
});

test("a predicate and an event type below the top are sentences too", () => {
  expect(filterLine({ kind: "predicate", name: "is_business_hours" }).said).toBe(
    "passes is_business_hours",
  );
  expect(filterLine({ kind: "on", types: ["a:x", "a:y", "a:z"] }).said).toBe(
    "the event is a:x, a:y or a:z",
  );
});

test("all, any and not nest as they nest in the rule", () => {
  const filter = {
    kind: "any",
    of: [
      { kind: "where", field: "service", op: "eq", value: "auth" },
      {
        kind: "all",
        of: [
          { kind: "where", field: "severity", op: "ge", value: 7 },
          { kind: "not", filter: { kind: "where", field: "muted", op: "exists" } },
        ],
      },
    ],
  };
  expect(stageText([filterLine(filter)])).toBe(
    [
      "any of",
      '  service = "auth"',
      "  all of",
      "    severity ≥ 7",
      "    not",
      "      muted exists",
    ].join("\n"),
  );
});

test("several filters beside the event types must each hold; none says none", () => {
  const two = withWhen({
    filter: {
      kind: "all",
      of: [
        on,
        { kind: "where", field: "a", op: "eq", value: 1 },
        { kind: "where", field: "b", op: "eq", value: 2 },
      ],
    },
  });
  expect(said(two, "filter")).toBe("a = 1\nand b = 2");
  expect(said(withWhen({}), "filter")).toBe("none");
  expect(
    said(
      { ...RULE, when: { filter: { kind: "where", field: "a", op: "eq", value: 1 } } },
      "event types",
    ),
  ).toBe("any event");
});

test("each pattern kind is said in words", () => {
  expect(said(withWhen({}), "pattern")).toBe("each event");
  expect(said(withWhen({ pattern: { kind: "each" } }), "pattern")).toBe("each event");
  expect(
    said(withWhen({ pattern: { kind: "count", at_least: 3, within: "PT1M" } }), "pattern"),
  ).toBe("3 or more within 1 minute");
  expect(
    said(
      withWhen({
        pattern: {
          kind: "sequence",
          steps: [
            { kind: "on", types: ["ci:deploy.started"] },
            { kind: "on", types: ["ci:deploy.failed"] },
          ],
          within: "PT10M",
        },
      }),
      "pattern",
    ),
  ).toBe(
    "these, in order, within 10 minutes\n  the event is ci:deploy.started\n  the event is ci:deploy.failed",
  );
  expect(said(withWhen({ pattern: { kind: "absence", within: "PT10M" } }), "pattern")).toBe(
    "quiet for 10 minutes, per scope seen",
  );
});

test("throttle, dedupe and scope say what they are, or that there is none", () => {
  expect(said(RULE, "throttle")).toBe("at most 1 per 15 minutes");
  expect(said(withWhen({}), "throttle")).toBe("none");
  expect(said(withWhen({ dedupe: { key: ["ticket"], within: "PT1H" } }), "dedupe")).toBe(
    "once per ticket within 1 hour",
  );
  expect(said(RULE, "scope")).toBe("per service");
  expect(said({ ...RULE, scope: { fields: ["service", "region"] } }, "scope")).toBe(
    "per service, region",
  );
  expect(said({ ...RULE, scope: { fields: [] } }, "scope")).toBe("one scope");
  const { scope: _, ...unscoped } = RULE;
  expect(said(unscoped, "scope")).toBe("one scope");
});

test("an action is its name, and its params as fields; retries have reflexr's defaults", () => {
  expect(said(RULE, "action")).toBe('page\nto: "oncall"\nurgent: true');
  // biome-ignore lint/suspicious/noThenProperty: a reflexr rule names its action `then`, as data, never awaited.
  const notify = { ...RULE, then: { action: "notify" } };
  expect(said(notify, "action")).toBe("notify");
  expect(said(RULE, "retries")).toBe(
    "up to 5 attempts, 1 second apart at first, ×2 each time, at most 5 minutes",
  );
  expect(said({ ...RULE, retry: { max_attempts: 1 } }, "retries")).toBe("1 attempt, no retries");
});

test("a part it doesn't know is JSON in its place, and the rest still reads", async () => {
  const newer = {
    ...RULE,
    when: { ...RULE.when, pattern: { kind: "rate", per: "PT1M" }, window: "PT5M" },
    priority: "high",
  };
  expect(said(newer, "pattern")).toBe('{"kind":"rate","per":"PT1M"}');
  expect(said(newer, "throttle")).toBe("at most 1 per 15 minutes");
  expect(said(newer, "more")).toBe('priority: "high"\nwhen.window: "PT5M"');
  const filter = filterLine({ kind: "all", of: [{ kind: "near", field: "geo" }] });
  expect(stageText([filter])).toBe('all of\n  {"kind":"near","field":"geo"}');

  const screen = await render(<RulePipeline rule={newer} />);
  await expect.element(screen.getByText('{"kind":"rate","per":"PT1M"}')).toBeVisible();
  await expect.element(screen.getByText("at most 1 per 15 minutes")).toBeVisible();
});

test("a rule artifact shows what its preview found, its pipeline and its JSON to copy", async () => {
  const screen = await render(
    <FiredContext value="It would have fired 4 times since 2026-10-21.">
      {rule.render({ rule: RULE })}
    </FiredContext>,
  );
  await expect
    .element(screen.getByText("It would have fired 4 times since 2026-10-21."))
    .toBeVisible();
  const pipeline = screen.getByRole("list", { name: "The rule, stage by stage" });
  await expect.element(pipeline).toBeVisible();
  await expect.element(screen.getByText("portal:ticket.opened")).toBeVisible();
  await expect.element(screen.getByText("3 or more within 1 minute")).toBeVisible();
  await screen.getByRole("button", { name: "The rule, as JSON" }).click();
  await expect.element(screen.getByRole("button", { name: /Copy/ })).toBeVisible();
  expect(await axeViolations(screen.container)).toEqual([]);
  expect(rule.title({ rule: RULE })).toBe("ops.page_on_fire");
  expect(rule.title({ rule: "not a rule" })).toBeNull();
  expect(rule.title({})).toBeNull();
});

test("data that holds no rule shows as JSON", async () => {
  const screen = await render(rule.render({ draft: 1 }));
  await expect.element(screen.getByText("draft")).toBeVisible();
  expect(rule.parts?.({ draft: 1 }).map((part) => part.name)).toEqual(["JSON"]);
});

test("what a preview found is read from the newest proposal of the artifact that says", () => {
  const proposal = (id: string, artifact: string, rationale: string) =>
    ({
      id,
      status: "accept",
      rationale,
      change: { type: "create_artifact", kind: "rule", artifact_id: artifact, data: {} },
    }) as unknown as Artifactr.Proposal;
  const proposals = [
    proposal("p1", "r1", "Page on fire.\n\nIt would have fired 2 times since 2026-10-20."),
    proposal(
      "p2",
      "r1",
      "Fewer.\n\nIt would have fired 1 time since 2026-10-21, among the newest events.",
    ),
    proposal("p3", "r2", "Nothing about firing."),
  ];
  expect(firedOf(proposals, "r1")).toBe(
    "It would have fired 1 time since 2026-10-21, among the newest events.",
  );
  expect(firedOf(proposals, "r2")).toBeNull();
});

test("an edit names each stage it changes, with what it was and what it would be, to a screen reader too", async () => {
  const after = {
    ...RULE,
    when: {
      filter: {
        kind: "all",
        of: [
          on,
          { kind: "where", field: "severity", op: "ge", value: 7 },
          { kind: "where", field: "env", op: "eq", value: "prod" },
        ],
      },
      pattern: RULE.when.pattern,
      throttle: { at_most: 1, per: "PT5M" },
    },
  };
  const screen = await render(
    <ProposedChanges
      before={{ rule: RULE }}
      after={{ rule: after }}
      renderer={rule}
      compare={compare}
    />,
  );
  const throttle = screen.getByRole("region", { name: "throttle" });
  await expect.element(throttle).toBeVisible();
  // Read as a screen reader reads it: what went, marked removed, and what came, marked added.
  expect(throttle.element().textContent).toContain("removed: 15");
  expect(throttle.element().textContent).toContain("added: 5");
  expect(throttle.element().querySelector("del")?.textContent).toContain("15");
  expect(throttle.element().querySelector("ins")?.textContent).toContain("5");
  const filter = screen.getByRole("region", { name: "filter" });
  // The filter added is the one line added: the rest is as it was.
  expect(filter.element().textContent).toContain('added: and env = "prod"');
  expect(filter.element().textContent).not.toContain("removed");
  // What didn't change isn't named.
  expect(screen.getByRole("region", { name: "pattern" }).query()).toBeNull();
  expect(screen.getByRole("region", { name: "action" }).query()).toBeNull();
  expect(await axeViolations(screen.container)).toEqual([]);
});
