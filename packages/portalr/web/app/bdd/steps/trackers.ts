import { expect } from "@playwright/test";
import { started, Then, When } from "./fixtures";
import { origin, runOf } from "./runs";

/** Where the test application's fake tracker links its items: checked, never opened. */
const TRACKER = "https://tracker.portalr.test/ops/";

/** A run's filing and its follower's read take a few of the reactor's and the follower's polls. */
const PATIENCE = { timeout: 15_000 };

Then("its run links to the item it was filed as, in Plane", async ({ page, scenario }) => {
  const filed = runOf(page, scenario.run)
    .getByRole("link", { name: /^OPS-\d+, in Plane\s\(opens in a new tab\)$/ })
    .first();
  await expect(filed).toBeVisible(PATIENCE);
  await expect(filed).toHaveAttribute("href", new RegExp(`^${TRACKER}\\d+$`));
  await expect(filed).toHaveAttribute("target", "_blank");
  await expect(filed).toHaveAttribute("rel", "noopener noreferrer");
  const name = (await filed.getAttribute("aria-label"))?.split(",")[0] ?? null;
  scenario.item = name;
});

When("someone renames that item in the tracker", async ({ request, scenario }) => {
  const name = started(scenario.item, "find the item a run was filed as");
  const renamed = await request.post(`${origin()}/tracker/edits`, {
    data: { name, title: `Renamed ${crypto.randomUUID().slice(0, 8)}` },
  });
  expect(renamed.status()).toBe(204);
});

Then("a follow-up run links to the item it came from", async ({ page, scenario }) => {
  const name = started(scenario.item, "find the item a run was filed as");
  const followUp = page
    .getByRole("table", { name: "Rules' runs" })
    .getByRole("row")
    .filter({ hasText: "portalr:follow-up" })
    .filter({ has: page.getByRole("link", { name: `${name}, in Plane (opens in a new tab)` }) });
  await expect(followUp).toHaveCount(1, PATIENCE);
  await expect(followUp.getByText("From")).toBeVisible();
  // Its "From" comes first; its chain, the filing run's, files it too.
  await expect(
    followUp.getByRole("link", { name: `${name}, in Plane (opens in a new tab)` }).first(),
  ).toHaveAttribute("href", new RegExp(`^${TRACKER}\\d+$`));
});
