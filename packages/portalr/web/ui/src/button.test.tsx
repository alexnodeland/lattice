import { expect, test, vi } from "vitest";
import { userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { Button } from "./button";
import { contrast, token } from "./test/colours";

test("a primary button is set in the working colour, readably", async () => {
  const screen = await render(<Button>Accept</Button>);
  const button = screen.getByRole("button", { name: "Accept" }).element();
  const style = getComputedStyle(button);
  expect(style.backgroundColor).toBe(token("accent"));
  expect(contrast(style.color, style.backgroundColor)).toBeGreaterThanOrEqual(4.5);
});

test("a secondary button sits on the surface", async () => {
  const screen = await render(<Button variant="secondary">Reject</Button>);
  const button = screen.getByRole("button", { name: "Reject" }).element();
  expect(getComputedStyle(button).backgroundColor).toBe(token("surface"));
});

test("a caller's classes override the button's own", async () => {
  const screen = await render(<Button className="bg-surface">Later</Button>);
  const button = screen.getByRole("button", { name: "Later" }).element();
  expect(button.classList).toContain("bg-surface");
  expect(button.classList).not.toContain("bg-accent");
});

test("a button reached by the keyboard shows the focus ring", async () => {
  const screen = await render(<Button>Open</Button>);
  await userEvent.tab();
  const button = screen.getByRole("button", { name: "Open" }).element();
  expect(button.matches(":focus-visible")).toBe(true);
  expect(getComputedStyle(button).outlineColor).toBe(token("focus"));
});

test("a button is pressed, unless it is disabled", async () => {
  const press = vi.fn();
  const screen = await render(
    <>
      <Button onClick={press}>Retry</Button>
      <Button onClick={press} disabled>
        Skip
      </Button>
    </>,
  );
  await screen.getByRole("button", { name: "Retry" }).click();
  await screen.getByRole("button", { name: "Skip" }).click({ force: true });
  expect(press).toHaveBeenCalledOnce();
});
