import { expect, test } from "vitest";
import { render } from "vitest-browser-react";
import { Plain } from "./plain";

test("a plain page links home by the lockup, holds the account, and has its one heading", async () => {
  const screen = await render(
    <Plain home={<a href="#home" />} title="acme" account={<button type="button">Account</button>}>
      <p>The workspaces in acme.</p>
    </Plain>,
  );
  await expect
    .element(screen.getByRole("link", { name: "portalr" }))
    .toHaveAttribute("href", "#home");
  await expect.element(screen.getByRole("button", { name: "Account" })).toBeVisible();
  await expect.element(screen.getByRole("heading", { level: 1 })).toHaveTextContent("acme");
  await expect.element(screen.getByRole("main")).toHaveTextContent("acmeThe workspaces in acme.");
});

test("signed out, a plain page has no account", async () => {
  const screen = await render(<Plain home={<a href="#home" />} title="Not found" />);
  expect(screen.container.querySelectorAll("button")).toHaveLength(0);
});
