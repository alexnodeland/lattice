import { type APIRequestContext, expect, type Page } from "@playwright/test";
import { Given, Then, When } from "./fixtures";
import { email, password } from "./people";

/** The workspace the scenarios' runs are in, in acme. */
const NOTES = "/reflexr/v1/workspaces/notes";

export const origin = () => new URL(process.env.PORTALR_APP_URL ?? "http://localhost:8000").origin;

/** A person's access token, as Supabase Auth issues it at the application's `/auth/v1`. */
async function token(request: APIRequestContext, person: string): Promise<string> {
  const signed = await request.post(`${origin()}/auth/v1/token?grant_type=password`, {
    data: { email: email(person), password: password(person) },
  });
  expect(signed.ok()).toBe(true);
  return ((await signed.json()) as { access_token: string }).access_token;
}

/** The signed-in person's token, in this page's session. */
export const session = (page: Page) =>
  page.evaluate(
    () =>
      (JSON.parse(localStorage.getItem("portalr") ?? "{}") as { access_token: string })
        .access_token,
  );

/** Publish a ticket as the token's person, and wait for the run of triage it sets off: its id. */
async function ticket(
  request: APIRequestContext,
  bearer: string,
  subject: string,
): Promise<string> {
  const headers = { Authorization: `Bearer ${bearer}`, "X-Tenant": "acme" };
  const published = await request.post(`${origin()}${NOTES}/events`, {
    headers,
    data: { event: { type: "portalr:ticket.opened", subject } },
  });
  expect(published.ok()).toBe(true);
  const [{ seq }] = (await published.json()) as [{ seq: number }];
  let run: string | undefined;
  await expect
    .poll(async () => {
      // triage's own: a stored rule another scenario installed may match the ticket too.
      const read = await request.get(`${origin()}${NOTES}/runs`, {
        headers,
        params: { rule: "portalr:triage" },
      });
      const runs = (await read.json()) as {
        id: string;
        matched: number[];
      }[];
      run = runs.find((each) => each.matched.includes(seq))?.id;
      return run;
    })
    .toBeDefined();
  return run as string;
}

const runOf = (page: Page, run: string | null) => {
  if (run === null) {
    throw new Error("no run was set off: publish a ticket first");
  }
  return page
    .getByRole("list", { name: "Rules' runs" })
    .getByRole("listitem", { name: `Run ${run}` });
};

const turnOf = (page: Page, thread: string | null) => {
  if (thread === null) {
    throw new Error("no thread was started: start one of their own first");
  }
  return page
    .getByRole("list", { name: "Turns" })
    .getByRole("listitem")
    .filter({ has: page.getByRole("link", { name: thread, exact: true }) })
    .first();
};

When("they publish a ticket that {word}", async ({ page, request, scenario }, outcome: string) => {
  const subject = `${outcome === "fails" ? "fail" : "triage"} ${crypto.randomUUID()}`;
  scenario.run = await ticket(request, await session(page), subject);
});

Given("bob has published a ticket that fails", async ({ request, scenario }) => {
  scenario.run = await ticket(request, await token(request, "bob"), `fail ${crypto.randomUUID()}`);
});

When("they start a thread of their own", async ({ page, scenario }) => {
  scenario.thread = `Thread ${crypto.randomUUID().slice(0, 8)}`;
  await page.getByLabel("New thread").fill(scenario.thread);
  await page.getByRole("button", { name: "Start" }).click();
  await expect(page.getByRole("heading", { level: 2 })).toHaveText(scenario.thread);
  scenario.threadUrl = page.url();
});

Then("its run is {string}", async ({ page, scenario }, status: string) => {
  await expect(runOf(page, scenario.run).getByRole("status")).toHaveText(status);
});

When("they {word} its run", async ({ page, scenario }, action: string) => {
  const name = action.charAt(0).toUpperCase() + action.slice(1);
  await runOf(page, scenario.run).getByRole("button", { name }).click();
});

When(
  "they find its run not helpful, saying {string}",
  async ({ page, scenario }, comment: string) => {
    const run = runOf(page, scenario.run);
    await run.getByRole("button", { name: "Not helpful" }).click();
    await run.getByRole("textbox", { name: "Why? (optional)" }).fill(comment);
    await run.getByRole("button", { name: "Add" }).click();
  },
);

Then("its run shows {string}", async ({ page, scenario }, text: string) => {
  await expect(runOf(page, scenario.run).getByText(text)).toBeVisible();
});

Then("their thread's turn is {string}", async ({ page, scenario }, status: string) => {
  await expect(turnOf(page, scenario.thread).getByRole("status")).toHaveText(status);
});

Then("their thread's turn has no Stop", async ({ page, scenario }) => {
  await expect(turnOf(page, scenario.thread).getByRole("button", { name: "Stop" })).toHaveCount(0);
});

When("they stop their thread's turn", async ({ page, scenario }) => {
  await turnOf(page, scenario.thread).getByRole("button", { name: "Stop" }).click();
});

When("they find their thread's turn helpful", async ({ page, scenario }) => {
  await turnOf(page, scenario.thread).getByRole("button", { name: "Helpful", exact: true }).click();
});

Then("their thread's turn shows them finding it helpful", async ({ page, scenario }) => {
  await expect(
    turnOf(page, scenario.thread).getByRole("button", { name: "Helpful", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
});

Then("they can't retry or skip its run", async ({ page, scenario }) => {
  // A viewer may give feedback on what they read, which grantr's viewer role holds.
  const run = runOf(page, scenario.run);
  await expect(run.getByRole("status")).toHaveText("Dead-lettered");
  await expect(run.getByRole("button", { name: "Helpful", exact: true })).toBeVisible();
  for (const action of ["Retry", "Skip", "Cancel"]) {
    await expect(run.getByRole("button", { name: action })).toHaveCount(0);
  }
});

Then("the server refuses their own retry of it", async ({ page, request, scenario }) => {
  // Hiding the button is no permission: grantr checks the command itself.
  const refused = await request.post(`${origin()}${NOTES}/commands`, {
    headers: { Authorization: `Bearer ${await session(page)}`, "X-Tenant": "acme" },
    data: {
      type: "command",
      command_id: crypto.randomUUID(),
      command: { type: "retry_run", run_id: scenario.run },
    },
  });
  expect(refused.status()).toBe(403);
});
