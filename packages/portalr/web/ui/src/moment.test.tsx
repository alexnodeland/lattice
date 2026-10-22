import { expect, test } from "vitest";
import { render } from "vitest-browser-react";
import { Ago, ago, Moment } from "./moment";

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

test("Ago says how long ago, with the moment on hover; one ahead of the clock is now", async () => {
  const now = new Date("2026-10-21T12:00:00Z");
  const screen = await render(
    <p>
      <Ago at="2026-10-21T11:55:00Z" now={now} />
      <Ago at="2026-10-21T12:03:00Z" now={now} />
    </p>,
  );
  const [past, ahead] = screen.container.querySelectorAll("time");
  expect(past?.getAttribute("dateTime")).toBe("2026-10-21T11:55:00Z");
  expect(past?.textContent).toBe("5 minutes ago");
  // The moment itself is on hover only: enough for a list read at a glance, and in `dateTime`.
  expect(past?.getAttribute("title")).toBe(new Date("2026-10-21T11:55:00Z").toLocaleString());
  expect(ahead?.textContent).toBe("now");
  expect(ahead?.getAttribute("dateTime")).toBe("2026-10-21T12:03:00Z");
});
