import { expect, test } from "vitest";
import { userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { SkipLink } from "./skip-link";

test("the skip link is the first stop, hidden until focused, and leads to the content", async () => {
  const screen = await render(
    <>
      <SkipLink />
      <button type="button">Menu</button>
      <main id="main" tabIndex={-1}>
        Content
      </main>
    </>,
  );
  const link = screen.getByRole("link", { name: "Skip to content" }).element();
  expect(link.getAttribute("href")).toBe("#main");
  expect(link.getBoundingClientRect().bottom).toBeLessThanOrEqual(0);
  await userEvent.tab();
  expect(document.activeElement).toBe(link);
  expect(link.getBoundingClientRect().top).toBeGreaterThanOrEqual(0);
});

test("in the frame, the skip link is the first stop, and following it focuses the content", async () => {
  const { RailShell } = await import("./rail-shell");
  const screen = await render(
    <RailShell home={<a href="#home" />} switcher={<span>acme</span>} account={<span>alice</span>}>
      Content
    </RailShell>,
  );
  await userEvent.tab();
  const link = screen.getByRole("link", { name: "Skip to content" }).element();
  expect(document.activeElement).toBe(link);
  await userEvent.keyboard("{Enter}");
  expect(document.activeElement?.id).toBe("main");
});

test("focused, the skip link takes a room of its own above the frame, and covers nothing", async () => {
  const { RailShell } = await import("./rail-shell");
  const screen = await render(
    <RailShell
      home={<a href="#home">Home</a>}
      switcher={<span>acme</span>}
      account={<span>alice</span>}
    >
      Content
    </RailShell>,
  );
  const header = document.querySelector("header") as HTMLElement;
  const before = header.getBoundingClientRect().top;
  await userEvent.tab();
  const link = screen.getByRole("link", { name: "Skip to content" }).element();
  expect(document.activeElement).toBe(link);
  const bar = link.getBoundingClientRect();
  expect(bar.height).toBeGreaterThan(0);
  expect(header.getBoundingClientRect().top).toBeGreaterThanOrEqual(before + bar.height - 1);
});

test("leaving the skip link gives its room back: the frame returns to the top", async () => {
  const { RailShell } = await import("./rail-shell");
  await render(
    <RailShell
      home={<a href="#home">Home</a>}
      switcher={<span>acme</span>}
      account={<span>alice</span>}
    >
      Content
    </RailShell>,
  );
  const header = document.querySelector("header") as HTMLElement;
  const before = header.getBoundingClientRect().top;
  await userEvent.tab();
  expect(header.getBoundingClientRect().top).toBeGreaterThan(before);
  await userEvent.tab();
  expect(header.getBoundingClientRect().top).toBe(before);
});
