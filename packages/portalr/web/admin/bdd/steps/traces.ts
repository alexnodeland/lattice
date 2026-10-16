import { expect, type Page } from "@playwright/test";
import { Given, Then, When } from "./fixtures";

When("they open Traces", async ({ page }) => {
  await page
    .getByRole("navigation", { name: "Tenant" })
    .getByRole("link", { name: "Traces" })
    .click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Traces");
});

/** What the page said last, for a wait that ends without a trace to say why. */
async function said(page: Page): Promise<string> {
  const alert = page.getByRole("alert");
  if ((await alert.count()) > 0) {
    return `the page said: ${(await alert.first().innerText()).trim()}`;
  }
  const none = page.getByRole("heading", { name: /^(No traces|Tempo isn't)/ });
  return (await none.count()) > 0
    ? `the page said: ${(await none.first().innerText()).trim()}`
    : "no trace was listed";
}

/**
 * Reads Traces again, from the top, until it lists a trace: Tempo takes a moment to hold what the
 * application sent. It ends with what the page said, such as that Tempo isn't answering.
 */
async function eventuallyListed(page: Page) {
  let last = "nothing was read";
  try {
    await expect
      .poll(
        async () => {
          await page.reload();
          await expect(page.getByRole("heading", { level: 1 })).toHaveText("Traces");
          const listed = await page
            .getByRole("table", { name: "Traces" })
            .getByRole("link")
            .count();
          if (listed === 0) {
            last = await said(page);
          }
          return listed;
        },
        { timeout: 40_000, intervals: [2_000] },
      )
      .toBeGreaterThanOrEqual(1);
  } catch (error) {
    throw new Error(`no trace was listed within 40 s: ${last}`, { cause: error });
  }
}

Then("a trace is eventually listed", async ({ page }) => {
  await eventuallyListed(page);
});

When("they open the newest trace", async ({ page }) => {
  await page.getByRole("table", { name: "Traces" }).getByRole("link").first().click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Trace");
});

Then("they see its spans as a tree", async ({ page }) => {
  const tree = page.getByRole("tree", { name: "Spans" });
  await expect(tree).toBeVisible();
  await expect(tree.getByRole("treeitem").first()).toBeVisible();
  // The first span is chosen, and its details are beside the tree.
  await expect(page.getByRole("region", { name: "Attributes" })).toBeVisible();
});

/** What a scenario's trace says: a phrase in its prompt, which must not reach the page unasked. */
const PROMPT = "Launch on Tuesday, said the user";

/** Every answer to a trace read, as the page got it: its address, and its body if it could be read. */
interface Answer {
  readonly url: URL;
  readonly body: string;
}
const answers = new WeakMap<Page, Promise<Answer | null>[]>();

/** The answers read so far, each awaited: a body a navigation discarded is none. */
const answered = async (page: Page) =>
  (await Promise.all(answers.get(page) ?? [])).filter((each): each is Answer => each !== null);

Given("a trace with a prompt has been sent for acme", async ({ request, page, made }) => {
  const thread = `thr_bdd_${crypto.randomUUID().replaceAll("-", "")}`;
  made.set("thread", thread);
  const hex = (bytes: number) =>
    crypto
      .randomUUID()
      .replaceAll("-", "")
      .slice(0, bytes * 2);
  const trace = hex(16);
  const root = hex(8);
  const now = BigInt(Date.now()) * 1_000_000n;
  const attributes = (values: Record<string, string>) =>
    Object.entries(values).map(([key, value]) => ({ key, value: { stringValue: value } }));
  const shared = { "tenant.id": "acme", "session.id": thread };
  const sent = await request.post(`${process.env.PORTALR_TEMPO_OTLP_URL}/v1/traces`, {
    data: {
      resourceSpans: [
        {
          resource: { attributes: attributes({ "service.name": "bdd-agent" }) },
          scopeSpans: [
            {
              scope: { name: "bdd" },
              spans: [
                {
                  traceId: trace,
                  spanId: root,
                  name: "invoke_workflow turn",
                  kind: 1,
                  startTimeUnixNano: String(now - 50_000_000n),
                  endTimeUnixNano: String(now),
                  attributes: attributes({ ...shared, "gen_ai.operation.name": "invoke_workflow" }),
                },
                {
                  traceId: trace,
                  spanId: hex(8),
                  parentSpanId: root,
                  name: "chat claude",
                  kind: 1,
                  startTimeUnixNano: String(now - 40_000_000n),
                  endTimeUnixNano: String(now - 10_000_000n),
                  attributes: attributes({
                    ...shared,
                    "gen_ai.operation.name": "chat",
                    "gen_ai.request.model": "claude",
                    // What a model call said, under names a denylist would have missed.
                    "gen_ai.input.messages": JSON.stringify([{ role: "user", content: PROMPT }]),
                    "pydantic_ai.all_messages": JSON.stringify([PROMPT]),
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
  // Every answer to a trace read, to see what reached the page before it was asked for.
  const seen: Promise<Answer | null>[] = [];
  answers.set(page, seen);
  page.on("response", (response) => {
    if (response.url().includes("/portalr/v1/traces/")) {
      seen.push(
        response.text().then(
          (body) => ({ url: new URL(response.url()), body }),
          () => null,
        ),
      );
    }
  });
});

When("they find that trace by its thread", async ({ page, made }) => {
  await page
    .getByRole("navigation", { name: "Tenant" })
    .getByRole("link", { name: "Traces" })
    .click();
  await page.getByRole("textbox", { name: "Thread" }).fill(made.get("thread") ?? "");
  await page.getByRole("button", { name: "Apply" }).click();
  await eventuallyListed(page);
});

When("they choose the span {string}", async ({ page }, name: string) => {
  await page
    .getByRole("tree", { name: "Spans" })
    .getByRole("treeitem", { name: new RegExp(`^${name},`) })
    .click();
  await expect(page.getByRole("region", { name })).toBeVisible();
});

Then("its prompt is not in the page, nor was it sent to it", async ({ page }) => {
  await expect(page.getByText(PROMPT)).toHaveCount(0);
  const read = await answered(page);
  expect(read.length).toBeGreaterThan(0);
  expect(read.filter((each) => each.body.includes(PROMPT))).toEqual([]);
});

Then("it names what it withheld", async ({ page }) => {
  const withheld = page.getByRole("region", { name: "Withheld" });
  await expect(withheld).toContainText("gen_ai.input.messages");
  await expect(withheld).toContainText("pydantic_ai.all_messages");
});

When("they ask to see what the span withheld", async ({ page }) => {
  await page.getByRole("button", { name: "Show what this span withheld" }).click();
});

Then("its prompt is in the page", async ({ page }) => {
  await expect(
    page.getByRole("region", { name: "Withheld" }).getByText(PROMPT).first(),
  ).toBeVisible();
  // It came in a read for that span, named, and not kept.
  const read = (await answered(page)).filter((each) => each.body.includes(PROMPT));
  expect(read).not.toEqual([]);
  expect(read.every((each) => each.url.searchParams.get("content") === "true")).toBe(true);
  expect(read.every((each) => (each.url.searchParams.get("span") ?? "") !== "")).toBe(true);
});

Then("no other span shows a prompt", async ({ page }) => {
  await page
    .getByRole("tree", { name: "Spans" })
    .getByRole("treeitem", { name: /^invoke_workflow turn,/ })
    .click();
  await expect(page.getByRole("region", { name: "Withheld" })).toHaveCount(0);
  await expect(page.getByText(PROMPT)).toHaveCount(0);
});
