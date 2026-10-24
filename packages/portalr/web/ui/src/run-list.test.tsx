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
