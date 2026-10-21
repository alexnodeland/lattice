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
  const { AppShell } = await import("./app-shell");
  const screen = await render(
    <AppShell home={<a href="#home" />} switcher={<span>acme</span>} account={<span>alice</span>}>
      Content
    </AppShell>,
  );
  await userEvent.tab();
  const link = screen.getByRole("link", { name: "Skip to content" }).element();
  expect(document.activeElement).toBe(link);
  await userEvent.keyboard("{Enter}");
  expect(document.activeElement?.id).toBe("main");
});
