import { expect, test } from "vitest";
import { render } from "vitest-browser-react";
import { Page } from "./page";

test("a page's title is its heading", async () => {
  const screen = await render(<Page title="portalr">Soon.</Page>);
  await expect.element(screen.getByRole("heading", { level: 1 })).toHaveTextContent("portalr");
  expect(screen.getByRole("main").element().textContent).toBe("portalrSoon.");
});
