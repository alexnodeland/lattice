import { afterEach, beforeEach, expect, test } from "vitest";
import { render } from "vitest-browser-react";
import { useAppearance } from "./appearance";

const KEY = "portalr-appearance";

function Scheme() {
  const [appearance, setAppearance] = useAppearance();
  return (
    <button type="button" onClick={() => setAppearance("dark")}>
      {appearance}
    </button>
  );
}

beforeEach(() => {
  localStorage.removeItem(KEY);
  delete document.documentElement.dataset.theme;
});

afterEach(() => {
  localStorage.removeItem(KEY);
  delete document.documentElement.dataset.theme;
});

test("the scheme starts on the system's, a choice sets data-theme and is kept", async () => {
  const screen = await render(<Scheme />);
  await expect.element(screen.getByRole("button", { name: "system" })).toBeVisible();
  await screen.getByRole("button", { name: "system" }).click();
  expect(document.documentElement.dataset.theme).toBe("dark");
  expect(localStorage.getItem(KEY)).toBe("dark");
});

test("another tab's choice of scheme is followed", async () => {
  const screen = await render(<Scheme />);
  localStorage.setItem(KEY, "light");
  window.dispatchEvent(new StorageEvent("storage", { key: KEY, newValue: "light" }));
  await expect.element(screen.getByRole("button", { name: "light" })).toBeVisible();
  expect(document.documentElement.dataset.theme).toBe("light");
});
