import { expect, test } from "vitest";
import { userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { Disclosure } from "./disclosure";
import { contrast, token } from "./test/colours";

test("a disclosure is a button that says whether it is open, and, open, what it opens; the keyboard works it", async () => {
  const screen = await render(<Disclosure summary="Show the figures">The figures</Disclosure>);
  const trigger = screen.getByRole("button", { name: "Show the figures" });
  await expect.element(trigger).toHaveAttribute("aria-expanded", "false");
  // Closed, what it opens is hidden until found, as a `details` element's is.
  expect(screen.getByText("The figures").element().closest("[hidden]")).not.toBeNull();
  await userEvent.tab();
  await expect.element(trigger).toHaveFocus();
  await userEvent.keyboard("{Enter}");
  await expect.element(trigger).toHaveAttribute("aria-expanded", "true");
  await expect.element(screen.getByText("The figures")).toBeVisible();
  // Open, it names what it opens.
  const panel = document.getElementById(trigger.element().getAttribute("aria-controls") ?? "");
  expect(panel?.textContent).toBe("The figures");
  await userEvent.keyboard(" ");
  await expect.element(trigger).toHaveAttribute("aria-expanded", "false");
});

test("its target is at least 24px tall, its focus ring the kit's, and its chevron still under reduced motion", async () => {
  const screen = await render(<Disclosure summary="Details">Why</Disclosure>);
  const trigger = screen.getByRole("button", { name: "Details" }).element();
  expect(trigger.getBoundingClientRect().height).toBeGreaterThanOrEqual(24);
  await userEvent.tab();
  const style = getComputedStyle(trigger);
  expect(style.outlineColor).toBe(token("focus"));
  expect(contrast(token("focus"), token("paper"))).toBeGreaterThanOrEqual(3);
  const chevron = trigger.querySelector("svg") as SVGElement;
  expect(getComputedStyle(chevron).transitionProperty).toBe("none");
});

test("whatever the look, a link's or a block's, it is the same button", async () => {
  const screen = await render(
    <>
      <Disclosure look="link" summary="Compare">
        Compared
      </Disclosure>
      <Disclosure look="block" summary={<span>Version 2</span>} defaultOpen>
        Opened
      </Disclosure>
    </>,
  );
  await expect
    .element(screen.getByRole("button", { name: "Compare" }))
    .toHaveAttribute("aria-expanded", "false");
  await expect
    .element(screen.getByRole("button", { name: "Version 2" }))
    .toHaveAttribute("aria-expanded", "true");
});
