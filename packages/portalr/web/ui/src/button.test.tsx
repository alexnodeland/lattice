import { expect, onTestFinished, test, vi } from "vitest";
import { commands, userEvent } from "vitest/browser";
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

test("a secondary button's edge stands out from the surface it sits on", async () => {
  const screen = await render(<Button variant="secondary">Deny</Button>);
  const style = getComputedStyle(screen.getByRole("button", { name: "Deny" }).element());
  expect(style.borderTopColor).toBe(token("edge"));
  expect(contrast(style.borderTopColor, token("paper"))).toBeGreaterThanOrEqual(3);
});

test("a danger button is in the danger colour, readably", async () => {
  const screen = await render(<Button variant="danger">Delete acme</Button>);
  const style = getComputedStyle(screen.getByRole("button", { name: "Delete acme" }).element());
  expect(style.backgroundColor).toBe(token("danger"));
  expect(contrast(style.color, style.backgroundColor)).toBeGreaterThanOrEqual(4.5);
});

test("a ghost button is bare until hovered", async () => {
  const screen = await render(<Button variant="ghost">More</Button>);
  const style = getComputedStyle(screen.getByRole("button", { name: "More" }).element());
  expect(style.backgroundColor).toBe("rgba(0, 0, 0, 0)");
  expect(style.color).toBe(token("fg"));
});

test("a disabled button is visibly so: a muted fill, the cursor that says so, its words still readable", async () => {
  const screen = await render(
    <>
      <Button disabled>Send</Button>
      <Button variant="secondary" disabled>
        Skip
      </Button>
    </>,
  );
  for (const name of ["Send", "Skip"]) {
    const style = getComputedStyle(screen.getByRole("button", { name }).element());
    expect(style.opacity, name).toBe("1");
    expect(style.cursor, name).toBe("not-allowed");
    expect(style.backgroundColor, name).toBe(token("line"));
    expect(style.color, name).toBe(token("muted"));
    expect(contrast(style.color, style.backgroundColor), name).toBeGreaterThanOrEqual(4.5);
  }
});

test("a small button is smaller than the default in its words and its padding, for a row", async () => {
  const screen = await render(
    <>
      <Button variant="ghost">Change</Button>
      <Button variant="ghost" size="sm">
        Remove
      </Button>
    </>,
  );
  const medium = getComputedStyle(screen.getByRole("button", { name: "Change" }).element());
  const small = getComputedStyle(screen.getByRole("button", { name: "Remove" }).element());
  expect(Number.parseFloat(small.fontSize)).toBeLessThan(Number.parseFloat(medium.fontSize));
  expect(Number.parseFloat(small.paddingLeft)).toBeLessThan(Number.parseFloat(medium.paddingLeft));
});

test("a ghost button is bare until it is hovered", async () => {
  const screen = await render(<Button variant="ghost">Retry</Button>);
  const button = screen.getByRole("button", { name: "Retry" });
  expect(getComputedStyle(button.element()).backgroundColor).toBe("rgba(0, 0, 0, 0)");
  await button.hover();
  await expect.poll(() => getComputedStyle(button.element()).backgroundColor).toBe(token("wash"));
});

test("a soft danger button offers a destructive action in the danger colour, readably, and washes it when hovered", async () => {
  const screen = await render(<Button variant="danger-soft">Remove</Button>);
  const button = screen.getByRole("button", { name: "Remove" });
  const style = getComputedStyle(button.element());
  expect(style.color).toBe(token("danger"));
  for (const ground of ["paper", "surface"]) {
    expect(contrast(style.color, token(ground))).toBeGreaterThanOrEqual(4.5);
  }
  expect(style.backgroundColor).toBe("rgba(0, 0, 0, 0)");
  await button.hover();
  await expect
    .poll(() => getComputedStyle(button.element()).backgroundColor)
    .not.toBe("rgba(0, 0, 0, 0)");
});

test("a pressed toggle takes the wash, in the working colour", async () => {
  const screen = await render(
    <Button variant="ghost" aria-pressed>
      Helpful
    </Button>,
  );
  const style = getComputedStyle(screen.getByRole("button", { name: "Helpful" }).element());
  expect(style.backgroundColor).toBe(token("wash"));
  expect(style.color).toBe(token("accent"));
  expect(contrast(style.color, style.backgroundColor)).toBeGreaterThanOrEqual(4.5);
});

test("a button changes colour at once when motion is reduced", async () => {
  onTestFinished(() => commands.reduceMotion(true));
  await commands.reduceMotion(false);
  const screen = await render(<Button>Approve</Button>);
  const button = screen.getByRole("button", { name: "Approve" }).element();
  expect(getComputedStyle(button).transitionProperty).not.toBe("none");
  await commands.reduceMotion(true);
  expect(getComputedStyle(button).transitionProperty).toBe("none");
});

/** A colour laid over a ground, as the screen shows it: `alpha` of `over` on `ground`, as `rgb()` colours. */
function laid(over: string, alpha: number, ground: string): string {
  const [a, b] = [over, ground].map((colour) => (colour.match(/[\d.]+/g) ?? []).map(Number));
  const mixed = [0, 1, 2].map((at) =>
    Math.round((a?.[at] ?? 0) * alpha + (b?.[at] ?? 0) * (1 - alpha)),
  );
  return `rgb(${mixed.join(", ")})`;
}

test("a soft danger button's hover tint is the danger colour at 12%, and its words read on it, on every ground", async () => {
  const screen = await render(<Button variant="danger-soft">Remove</Button>);
  const button = screen.getByRole("button", { name: "Remove" });
  await button.hover();
  await expect
    .poll(() => getComputedStyle(button.element()).backgroundColor)
    .not.toBe("rgba(0, 0, 0, 0)");
  const style = getComputedStyle(button.element());
  // A tint with alpha: as `color(srgb r g b / a)`, whose alpha is the 12% the variant mixes in.
  expect(style.backgroundColor).toMatch(/\/ 0\.12\)|0\.12\)/);
  for (const ground of ["paper", "surface"]) {
    const tinted = laid(token("danger"), 0.12, token(ground));
    expect(contrast(token("danger"), tinted), ground).toBeGreaterThanOrEqual(4.5);
  }
});

test("colour-blind mode leaves the danger colour and its tint as they are", async () => {
  const screen = await render(<Button variant="danger-soft">Remove</Button>);
  const before = getComputedStyle(screen.getByRole("button", { name: "Remove" }).element()).color;
  document.documentElement.dataset.cvd = "";
  onTestFinished(() => {
    delete document.documentElement.dataset.cvd;
  });
  expect(getComputedStyle(screen.getByRole("button", { name: "Remove" }).element()).color).toBe(
    before,
  );
});

test("a pending button can't be pressed again, looks disabled, and keeps the focus it was pressed with", async () => {
  const press = vi.fn();
  const screen = await render(
    <Button pending onClick={press}>
      Accept
    </Button>,
  );
  const button = screen.getByRole("button", { name: "Accept" });
  button.element().focus();
  expect(document.activeElement).toBe(button.element());
  await button.click({ force: true });
  expect(press).not.toHaveBeenCalled();
  await expect.element(button).toHaveAttribute("aria-disabled", "true");
  const style = getComputedStyle(button.element());
  expect(style.backgroundColor).toBe(token("line"));
  expect(style.cursor).toBe("not-allowed");
  expect(document.activeElement).toBe(button.element());
});
