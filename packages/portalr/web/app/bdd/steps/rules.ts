import { expect, type Page } from "@playwright/test";
import { Given, Then, When } from "./fixtures";
import { origin, session } from "./runs";

/** A ticket's filter, and a throttle within the test application's limits. */
const THROTTLED = {
  filter: { kind: "on", types: ["portalr:ticket.opened"] },
  throttle: { at_most: 10, per: "PT1H" },
};

/**
 * A stored rule the test application allows, as the JSON a person types: it triages tickets
 * again. It's text, as the field takes it, and since a rule's `then` is no promise's.
 */
const ruleOf = (name: string, description: string, when: object = THROTTLED) =>
  `{
  "name": ${JSON.stringify(name)},
  "description": ${JSON.stringify(description)},
  "when": ${JSON.stringify(when)},
  "then": { "action": "triage" },
  "ordering": "none",
  "timeout": "PT30S"
}`;

const own = (rule: string | null) => {
  if (rule === null) {
    throw new Error("no rule was installed: install one of their own first");
  }
  return rule;
};

const listed = (page: Page, rule: string) =>
  page.getByRole("list", { name: "Rules" }).getByRole("listitem", { name: `Rule ${rule}` });

const field = (page: Page) => page.getByRole("textbox", { name: "Rule, as reflexr's JSON" });

/** Fill the field with the rule's JSON, and send it with the button. */
async function send(page: Page, rule: string, button: string) {
  // Installing is folded under its button until asked (portalr ADR-0085).
  const install = page.getByRole("button", { name: "Install a rule…" });
  if ((await install.count()) > 0 && (await install.getAttribute("aria-expanded")) === "false") {
    await install.click();
  }
  await field(page).fill(rule);
  await page.getByRole("button", { name: button, exact: true }).click();
}

When("they install a rule of their own", async ({ page, scenario }) => {
  scenario.rule = `tickets:r${crypto.randomUUID().slice(0, 8)}`;
  await send(page, ruleOf(scenario.rule, "Triage it again"), "Install");
});

When("they install a rule with no throttle", async ({ page }) => {
  const name = `tickets:r${crypto.randomUUID().slice(0, 8)}`;
  await send(page, ruleOf(name, "Unbounded", { filter: THROTTLED.filter }), "Install");
});

When("they install a rule whose throttle allows {string}", async ({ page }, times: string) => {
  const name = `tickets:r${crypto.randomUUID().slice(0, 8)}`;
  const when = { ...THROTTLED, throttle: { ...THROTTLED.throttle, at_most: times } };
  await send(page, ruleOf(name, "Mistyped", when), "Install");
});

When("they install {string}", async ({ page }, text: string) => {
  await send(page, text, "Install");
});

Then("the field says {string}", async ({ page }, text: string) => {
  await expect(field(page)).toHaveAccessibleDescription(new RegExp(text));
});

Then("their rule is listed {string}", async ({ page, scenario }, text: string) => {
  await expect(listed(page, own(scenario.rule))).toContainText(text);
});

Then("their rule isn't listed", async ({ page, scenario }) => {
  await expect(listed(page, own(scenario.rule))).toHaveCount(0);
});

Then("the rule {string} is listed {string}", async ({ page }, rule: string, text: string) => {
  await expect(listed(page, rule)).toContainText(text);
});

Then("the schedule {string} is listed", async ({ page }, schedule: string) => {
  await expect(
    page.getByRole("list", { name: "Schedules" }).getByRole("listitem", {
      name: `Schedule ${schedule}`,
    }),
  ).toBeVisible();
});

Then("they can't install a rule", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "Rules", level: 1 })).toBeVisible();
  await expect(page.getByRole("button", { name: "Install" })).toHaveCount(0);
});

When("they open the rule {string}", async ({ page }, rule: string) => {
  await listed(page, rule).getByRole("link", { name: rule }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(rule);
});

When("they open their rule", async ({ page, scenario }) => {
  const rule = own(scenario.rule);
  await listed(page, rule).getByRole("link", { name: rule }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(rule);
});

Then("they can't edit or archive it", async ({ page }) => {
  // It reads as When and Then; its JSON is folded under them (portalr ADR-0085).
  await expect(page.getByText("When", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "The rule, as reflexr's JSON" }).click();
  await expect(page.getByText(/"description"/)).toBeVisible();
  await expect(field(page)).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Archive" })).toHaveCount(0);
});

When("they describe their rule as {string}", async ({ page, scenario }, text: string) => {
  await send(page, ruleOf(own(scenario.rule), text), "Save");
});

When(
  "they change only its description, in the JSON shown, to {string}",
  async ({ page }, text: string) => {
    const rule = JSON.parse(await field(page).inputValue());
    await send(page, JSON.stringify({ ...rule, description: text }, null, 2), "Save");
  },
);

When("they load version {int}", async ({ page }, version: number) => {
  await page.getByRole("button", { name: `Load version ${version}` }).click();
});

When("they open their rule's page again", async ({ page, scenario }) => {
  const rule = own(scenario.rule);
  await page.goto(`${page.url().replace(/\/rules$/, "")}/rules/${encodeURIComponent(rule)}`);
});

Given(
  "the rule is changed elsewhere to {string}",
  async ({ page, request, scenario }, text: string) => {
    const updated = await request.post(`${origin()}/reflexr/v1/workspaces/notes/commands`, {
      headers: { Authorization: `Bearer ${await session(page)}`, "X-Tenant": "acme" },
      data: {
        type: "command",
        command_id: `elsewhere-${crypto.randomUUID()}`,
        command: {
          type: "update_rule",
          rule: JSON.parse(ruleOf(own(scenario.rule), text)),
          provenance: {},
        },
      },
    });
    expect(updated.ok()).toBe(true);
  },
);

When("they archive their rule", async ({ page }) => {
  await page.getByRole("button", { name: "Archive" }).click();
  await page.getByRole("alertdialog").getByRole("button", { name: "Archive the rule" }).click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Rules");
});
