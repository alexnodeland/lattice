import { expect, test } from "vitest";
import { page } from "vitest/browser";
import { render } from "vitest-browser-react";
import { RunList, type RunParts } from "./run-list";

const RUN: RunParts = {
  key: "run_1",
  name: "Turn run_1",
  status: "Done",
  title: "Launch plan",
  started: <time dateTime="2026-10-23T09:00:00Z">Oct 23 09:00</time>,
  feedback: null,
  actions: null,
};

test("a list's runs say when each started, in a column of its own", async () => {
  await page.viewport(1280, 900);
  const screen = await render(
    <RunList
      caption="Turns"
      title="Thread"
      runs={[RUN]}
      started
      attempts={false}
      feedback={false}
    />,
  );
  const table = screen.getByRole("table", { name: "Turns" });
  await expect.element(table.getByRole("columnheader", { name: "Started" })).toBeVisible();
  await expect
    .element(table.getByRole("row", { name: "Turn run_1" }).getByText("Oct 23 09:00"))
    .toBeVisible();
});

test("a list with no runs says so, rather than draw a table with no rows", async () => {
  await page.viewport(1280, 900);
  const screen = await render(
    <RunList
      caption="Rules' runs"
      title="Rule"
      runs={[]}
      attempts
      feedback={false}
      empty={{ title: "No rule runs yet", body: "A rule's runs are listed here as it fires." }}
    />,
  );
  await expect.element(screen.getByText("No rule runs yet")).toBeVisible();
  expect(screen.getByRole("table").elements()).toHaveLength(0);
});

test("thumbs are quiet: shown in the table as the row is hovered, and in a phone's row's menu", async () => {
  await page.viewport(1280, 900);
  const thumbs = { given: null, onThumbs: async () => ({ outcome: "done" }) as const };
  const runs = [
    { ...RUN, attempts: 1, feedback: thumbs },
    { ...RUN, key: "run_2", name: "Run run_2", attempts: 3, feedback: thumbs },
  ];
  const list = <RunList caption="Runs" title="Rule" runs={runs} attempts feedback />;
  const screen = await render(list);
  const row = screen.getByRole("row", { name: "Turn run_1" });
  const quiet = row.getByRole("group", { name: "Feedback" }).element().parentElement as Element;
  expect(getComputedStyle(quiet).opacity).toBe("0");
  await row.hover();
  await expect.poll(() => getComputedStyle(quiet).opacity).toBe("1");
  // The first attempt goes without saying; a third is said.
  expect(row.element().querySelector("[data-num]")?.textContent).toBe("");
  await expect.element(screen.getByRole("row", { name: "Run run_2" }).getByText("3")).toBeVisible();
  await page.viewport(390, 900);
  const phone = screen.getByRole("list", { name: "Runs" });
  await expect.element(phone.getByText("Attempt 3")).toBeVisible();
  expect(phone.getByText("Attempt 1").elements()).toHaveLength(0);
  await phone.getByRole("button", { name: "Feedback on Turn run_1" }).click();
  await expect.element(page.getByRole("menuitemcheckbox", { name: "Helpful" })).toBeVisible();
});
