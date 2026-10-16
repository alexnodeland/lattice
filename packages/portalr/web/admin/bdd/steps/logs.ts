import { expect, type Page } from "@playwright/test";
import { Given, Then, When } from "./fixtures";

When("they open Logs", async ({ page }) => {
  await page
    .getByRole("navigation", { name: "Tenant" })
    .getByRole("link", { name: "Logs" })
    .click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Logs");
});

/** What a scenario's record says: a phrase in its line, which must not reach the page unasked. */
const PHRASE = "Launch on Tuesday, said the user";

/** Every answer to a log read, as the page got it: its address, and its body if it could be read. */
interface Answer {
  readonly url: URL;
  readonly body: string;
}
const answers = new WeakMap<Page, Promise<Answer | null>[]>();

/** The answers read so far, each awaited: a body a navigation discarded is none. */
const answered = async (page: Page) =>
  (await Promise.all(answers.get(page) ?? [])).filter((each): each is Answer => each !== null);

Given("a log record with a phrase has been sent for acme", async ({ request, page, made }) => {
  const thread = `thr_bdd_${crypto.randomUUID().replaceAll("-", "")}`;
  made.set("thread", thread);
  const attributes = (values: Record<string, string>) =>
    Object.entries(values).map(([key, value]) => ({ key, value: { stringValue: value } }));
  const sent = await request.post(`${process.env.PORTALR_LOKI_OTLP_URL}/otlp/v1/logs`, {
    data: {
      resourceLogs: [
        {
          resource: { attributes: attributes({ "service.name": "bdd-agent" }) },
          scopeLogs: [
            {
              scope: { name: "bdd" },
              logRecords: [
                {
                  timeUnixNano: String(BigInt(Date.now()) * 1_000_000n),
                  severityText: "INFO",
                  body: { stringValue: PHRASE },
                  attributes: attributes({
                    "tenant.id": "acme",
                    "artifactr.thread_id": thread,
                  }),
                },
              ],
            },
          ],
        },
      ],
    },
  });
  expect(sent.ok()).toBe(true);
  // Every answer to a log read, to see what reached the page before it was asked for.
  const seen: Promise<Answer | null>[] = [];
  answers.set(page, seen);
  page.on("response", (response) => {
    if (response.url().includes("/portalr/v1/logs")) {
      seen.push(
        response.text().then(
          (body) => ({ url: new URL(response.url()), body }),
          () => null,
        ),
      );
    }
  });
});

/**
 * Reads Logs again, with the thread, until it lists the record: Loki takes a moment to hold what
 * the application sent.
 */
When("they find that record by its thread", async ({ page, made }) => {
  const thread = made.get("thread") ?? "";
  await expect
    .poll(
      async () => {
        await page.goto(`${new URL(page.url()).pathname}?thread=${encodeURIComponent(thread)}`);
        await expect(page.getByRole("heading", { level: 1 })).toHaveText("Logs");
        return page.getByRole("option").count();
      },
      { timeout: 40_000, intervals: [2_000], message: "no record was listed within 40 s" },
    )
    .toBeGreaterThanOrEqual(1);
});

Then("its phrase is not in the page, nor was it sent to it", async ({ page }) => {
  await expect(page.getByText(PHRASE)).toHaveCount(0);
  const read = await answered(page);
  expect(read.length).toBeGreaterThan(0);
  expect(read.filter((each) => each.body.includes(PHRASE))).toEqual([]);
});

Then("it names the length of its line", async ({ page }) => {
  await expect(page.getByRole("region").filter({ hasText: "Line" }).first()).toContainText(
    `${PHRASE.length} characters`,
  );
});

When("they ask to see its line", async ({ page }) => {
  await page.getByRole("button", { name: "Show this line" }).click();
});

Then("its phrase is in the page", async ({ page }) => {
  await expect(page.getByRole("region", { name: "Line" }).getByText(PHRASE)).toBeVisible();
});

Then("the phrase came in a read for that record alone", async ({ page }) => {
  const read = (await answered(page)).filter((each) => each.body.includes(PHRASE));
  expect(read).toHaveLength(1);
  expect(read[0]?.url.pathname).toMatch(/\/portalr\/v1\/logs\/\d+-[0-9a-f]{16}$/);
});

Then("they see the health charts, or why there are none", async ({ page }) => {
  const health = page.getByRole("region", { name: "Health" });
  await expect(health).toBeVisible();
  await expect(
    health.getByRole("figure").or(health.getByRole("heading", { name: /^(No |Prometheus isn't)/ })),
  ).not.toHaveCount(0);
});

Then("each point is said to be a minute", async ({ page }) => {
  await expect(page.getByText("Each point is 1 minute.")).toBeVisible();
});
