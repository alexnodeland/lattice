import { expect, test } from "vitest";
import { userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { axeViolations } from "./test/axe";
import { contrast, token } from "./test/colours";
import { FILED, UNLINKED } from "./test/tracker-items";
import { TrackerItems, trackerName } from "./tracker-items";

test("each item opens in its tracker, in a new tab, named aloud with where it goes", async () => {
  const screen = await render(<TrackerItems label="Filed as" items={FILED} />);
  const plane = screen.getByRole("link", { name: "OPS-12, in Plane (opens in a new tab)" });
  await expect.element(plane).toHaveAttribute("href", "https://plane.example/acme/browse/OPS-12/");
  await expect.element(plane).toHaveAttribute("target", "_blank");
  await expect.element(plane).toHaveAttribute("rel", "noopener noreferrer");
  await expect
    .element(screen.getByRole("link", { name: "#41, in Vikunja (opens in a new tab)" }))
    .toHaveAttribute("href", "https://vikunja.example/tasks/41");
  await expect.element(screen.getByText("Filed as")).toBeVisible();
  expect(await axeViolations(screen.container)).toEqual([]);
});

test("a deleted item is its name alone, struck through and said in words", async () => {
  const screen = await render(<TrackerItems label="Filed as" items={FILED} />);
  expect(screen.getByRole("link").all()).toHaveLength(2);
  const name = screen.getByText("OPS-9", { exact: true }).element();
  expect(getComputedStyle(name).textDecorationLine).toBe("line-through");
  await expect.element(screen.getByText(", deleted")).toBeVisible();
});

test("an address no browser opens as a page, or none, is a name and never a link", async () => {
  const screen = await render(<TrackerItems label="From" items={UNLINKED} />);
  expect(screen.getByRole("link").all()).toHaveLength(0);
  await expect.element(screen.getByText("OPS-3", { exact: true })).toBeVisible();
  await expect.element(screen.getByText(", in linear")).toBeInTheDocument();
});

test("no items is nothing at all", async () => {
  const screen = await render(<TrackerItems label="Filed as" items={[]} />);
  expect(screen.container.textContent).toBe("");
});

test("a link is in the working colour, readable, and shows the focus ring from the keyboard", async () => {
  const screen = await render(<TrackerItems label="Filed as" items={FILED.slice(0, 1)} />);
  await userEvent.tab();
  const link = screen.getByRole("link").element();
  const style = getComputedStyle(link);
  expect(style.color).toBe(token("accent"));
  expect(contrast(style.color, token("paper"))).toBeGreaterThanOrEqual(4.5);
  expect(link.matches(":focus-visible")).toBe(true);
  expect(style.outlineColor).toBe(token("focus"));
});

test("a tracker is named as people name it, and one lattice doesn't know by its own name", () => {
  expect([trackerName("plane"), trackerName("vikunja"), trackerName("linear")]).toEqual([
    "Plane",
    "Vikunja",
    "linear",
  ]);
});
