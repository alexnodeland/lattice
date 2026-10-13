import { expect, test } from "vitest";
import { render } from "vitest-browser-react";
import { ago, Moment } from "./moment";

const now = new Date("2026-10-13T12:00:00Z");

test("how long ago a moment was, in its largest whole unit", () => {
  expect(ago(new Date("2026-10-13T11:59:30Z"), now)).toBe("30 seconds ago");
  expect(ago(new Date("2026-10-13T09:00:00Z"), now)).toBe("3 hours ago");
  expect(ago(new Date("2026-10-12T12:00:00Z"), now)).toBe("yesterday");
  expect(ago(now, now)).toBe("now");
});

test("a moment shows its time, and how long ago it was on hover", async () => {
  const screen = await render(<Moment at="2026-10-13T09:00:00Z" now={now} />);
  const time = screen.getByText(new Date("2026-10-13T09:00:00Z").toLocaleString());
  await expect.element(time).toHaveAttribute("datetime", "2026-10-13T09:00:00Z");
  await expect.element(time).toHaveAttribute("title", "3 hours ago");
});
