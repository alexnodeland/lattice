import { expect, test } from "vitest";
import { render } from "vitest-browser-react";
import { Switch } from "./switch";
import { token } from "./test/colours";

test("a switch turns on, and its track takes the working colour", async () => {
  const screen = await render(<Switch aria-label="Notices" />);
  const control = screen.getByRole("switch", { name: "Notices" });
  await expect.element(control).not.toBeChecked();
  await control.click();
  await expect.element(control).toBeChecked();
  expect(getComputedStyle(control.element()).backgroundColor).toBe(token("accent"));
});
