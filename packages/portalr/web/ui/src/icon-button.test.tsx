import { Maximize2 } from "lucide-react";
import type { ComponentProps } from "react";
import { expect, onTestFinished, test } from "vitest";
import { page, userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { IconButton } from "./icon-button";
import { token } from "./test/colours";

test("an icon button is named by its label, a target 24px or more, its icon hidden", async () => {
  const screen = await render(<IconButton label="Full view" icon={Maximize2} />);
  const button = screen.getByRole("button", { name: "Full view" }).element();
  const box = button.getBoundingClientRect();
  expect(box.width).toBeGreaterThanOrEqual(24);
  expect(box.height).toBeGreaterThanOrEqual(24);
  expect(button.querySelector("svg")?.getAttribute("aria-hidden")).toBe("true");
});

test("its label shows as a tooltip when the keyboard reaches it", async () => {
  await render(<IconButton label="Full view" icon={Maximize2} />);
  await userEvent.tab();
  const tip = page.getByText("Full view", { exact: true });
  await expect.element(tip).toBeVisible();
  expect(getComputedStyle(tip.element()).color).toBe(token("fg"));
});

test("a pressed icon button says so, in the wash", async () => {
  const screen = await render(<IconButton label="Helpful" icon={Maximize2} aria-pressed />);
  const button = screen.getByRole("button", { name: "Helpful", pressed: true }).element();
  expect(getComputedStyle(button).color).toBe(token("accent"));
});

test("an icon button can be a link, such as the router's", async () => {
  const screen = await render(
    <IconButton label="Open its page" icon={Maximize2} render={<a href="#page">page</a>} />,
  );
  const link = screen.getByRole("link", { name: "Open its page" }).element();
  expect(link.getAttribute("href")).toBe("#page");
});

test("a link icon button has the button's look, named by its label, not its element's words", async () => {
  const screen = await render(
    <IconButton label="Open its page" icon={Maximize2} render={<a href="#page">its words</a>} />,
  );
  const link = screen.getByRole("link", { name: "Open its page" }).element();
  expect(getComputedStyle(link).borderTopStyle).toBe("solid");
  // The element's own words are replaced by the icon: the square holds nothing else.
  expect(link.textContent).toBe("");
  expect(getComputedStyle(link).color).toBe(token("fg"));
});

test("Escape dismisses its tooltip", async () => {
  await render(<IconButton label="Full view" icon={Maximize2} />);
  await userEvent.tab();
  await expect.element(page.getByText("Full view", { exact: true })).toBeVisible();
  await userEvent.keyboard("{Escape}");
  await expect.element(page.getByText("Full view", { exact: true })).not.toBeInTheDocument();
});

test("a disabled icon button keeps its name, and isn't a stop for the keyboard", async () => {
  const screen = await render(
    <>
      <IconButton label="Helpful" icon={Maximize2} disabled />
      <button type="button">After</button>
    </>,
  );
  await expect.element(screen.getByRole("button", { name: "Helpful" })).toBeDisabled();
  await userEvent.tab();
  expect(document.activeElement?.textContent).toBe("After");
});

test("a link icon button keeps the link element's own handlers", async () => {
  let focused = false;
  await render(
    <IconButton
      label="Open its page"
      icon={Maximize2}
      render={
        <a href="#page" onFocus={() => (focused = true)}>
          page
        </a>
      }
    />,
  );
  await userEvent.tab();
  expect(focused).toBe(true);
  await expect.element(page.getByText("Open its page", { exact: true })).toBeVisible();
});

test("a pending icon button stays in reach of the keyboard, disabled", async () => {
  const screen = await render(
    <IconButton label="Helpful" icon={Maximize2} disabled focusableWhenDisabled />,
  );
  await userEvent.tab();
  const button = screen.getByRole("button", { name: "Helpful" }).element();
  expect(document.activeElement).toBe(button);
  expect(button.getAttribute("aria-disabled")).toBe("true");
});

test("Enter and Space on a disabled icon button in reach of the keyboard do nothing", async () => {
  let pressed = 0;
  await render(
    <IconButton
      label="Helpful"
      icon={Maximize2}
      disabled
      focusableWhenDisabled
      onClick={() => (pressed += 1)}
    />,
  );
  await userEvent.tab();
  await userEvent.keyboard("{Enter}");
  await userEvent.keyboard(" ");
  expect(pressed).toBe(0);
});

/** A router's link, as TanStack's renders one: an anchor with its own click. */
function RouterLink(props: ComponentProps<"a">) {
  return <a {...props}>{props.children}</a>;
}

test("a link icon button's own click runs, as a router's does to follow it", async () => {
  onTestFinished(() => history.replaceState(null, "", location.pathname + location.search));
  let followed = "";
  const screen = await render(
    <IconButton
      label="Open its page"
      icon={Maximize2}
      render={
        <RouterLink
          href="#page"
          onClick={(event) => {
            event.preventDefault();
            followed = "page";
          }}
        />
      }
    />,
  );
  await screen.getByRole("link", { name: "Open its page" }).click();
  expect(followed).toBe("page");
  expect(location.hash).not.toBe("#page");
});
