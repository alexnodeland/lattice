import { expect, onTestFinished, test } from "vitest";
import { commands, userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { Disclosure } from "./disclosure";
import { contrast, token } from "./test/colours";

test("a disclosure is a button that says whether it is open, and, open, what it opens; the keyboard works it", async () => {
  const screen = await render(<Disclosure summary="Show the figures">The figures</Disclosure>);
  const trigger = screen.getByRole("button", { name: "Show the figures" });
  await expect.element(trigger).toHaveAttribute("aria-expanded", "false");
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

test("closed, what it holds is hidden until found, and a find in the page opens it", async () => {
  const screen = await render(<Disclosure summary="Show the figures">Forty-two</Disclosure>);
  const hidden = screen.getByText("Forty-two").element().closest("[hidden]");
  expect(hidden?.getAttribute("hidden")).toBe("until-found");
  hidden?.dispatchEvent(new Event("beforematch", { bubbles: true }));
  await expect
    .element(screen.getByRole("button", { name: "Show the figures" }))
    .toHaveAttribute("aria-expanded", "true");
});

test("its chevron turns in the kit's time where motion is wanted", async () => {
  await commands.reduceMotion(false);
  onTestFinished(() => commands.reduceMotion(true));
  await expect.poll(() => matchMedia("(prefers-reduced-motion: reduce)").matches).toBe(false);
  const screen = await render(<Disclosure summary="Details">Why</Disclosure>);
  const chevron = screen.getByRole("button", { name: "Details" }).element().querySelector("svg");
  const style = getComputedStyle(chevron as SVGElement);
  // The token, resolved as the browser resolves it.
  const probe = document.createElement("span");
  probe.style.transitionDuration = "var(--disclosure-duration)";
  document.body.append(probe);
  const kit = getComputedStyle(probe).transitionDuration;
  probe.remove();
  expect(style.transitionProperty).toContain("transform");
  expect(Number.parseFloat(kit)).toBeGreaterThan(0);
  expect(style.transitionDuration).toBe(kit);
});

test("held open by its caller, opened at first, and each look a target at least 24px tall", async () => {
  const opened: boolean[] = [];
  const screen = await render(
    <>
      <Disclosure summary="Held" open={false} onOpenChange={(next) => opened.push(next)}>
        Held content
      </Disclosure>
      <Disclosure summary="At first" defaultOpen>
        First content
      </Disclosure>
      <Disclosure summary="A link" look="link">
        Linked
      </Disclosure>
    </>,
  );
  await screen.getByRole("button", { name: "Held" }).click();
  expect(opened).toEqual([true]);
  await expect
    .element(screen.getByRole("button", { name: "Held" }))
    .toHaveAttribute("aria-expanded", "false");
  await expect.element(screen.getByText("First content")).toBeVisible();
  for (const name of ["Held", "A link"]) {
    const height = screen.getByRole("button", { name }).element().getBoundingClientRect().height;
    expect(height).toBeGreaterThanOrEqual(24);
  }
});
