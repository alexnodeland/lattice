import type { ReactNode } from "react";
import { expect, onTestFinished, test } from "vitest";
import { render } from "vitest-browser-react";
import { AppShell } from "./app-shell";
import { type Brand, BrandContext } from "./brand";
import { Lockup } from "./marks";
import { SignIn } from "./sign-in";

const BRAND: Brand = {
  hash: "0123456789abcdef",
  identity: { product: "Nightshade", app: "Nightshade", admin: "Nightshade admin" },
  copy: { tagline: "Ask, and it is drafted.", signIn: "Sign in to Nightshade" },
  stylesheet: "brand/0123456789abcdef/brand.css",
  mark: {
    light: "brand/0123456789abcdef/assets/mark-light.svg",
    dark: "brand/0123456789abcdef/assets/mark-dark.svg",
  },
  favicon: "brand/0123456789abcdef/assets/favicon.svg",
};

const branded = (children: ReactNode, brand: Brand = BRAND) => (
  <BrandContext value={brand}>{children}</BrandContext>
);

test("with a kit, the lockup is its mark and the product's name in words", async () => {
  const screen = await render(branded(<Lockup ui="admin" />));
  await expect.element(screen.getByText("Nightshade admin")).toBeVisible();
  const marks = [...screen.container.querySelectorAll("img")];
  expect(marks.map((mark) => mark.getAttribute("src"))).toEqual([
    "/portalr/brand/0123456789abcdef/assets/mark-light.svg",
    "/portalr/brand/0123456789abcdef/assets/mark-dark.svg",
  ]);
  expect(marks.every((mark) => mark.getAttribute("alt") === "")).toBe(true);
});

test("the kit's mark for the page's scheme is the one shown, the system's or the person's", async () => {
  const screen = await render(branded(<Lockup />));
  const [light, dark] = [...screen.container.querySelectorAll("img")] as HTMLImageElement[];
  const system = matchMedia("(prefers-color-scheme: dark)").matches;
  expect(getComputedStyle(light as Element).display === "none").toBe(system);
  expect(getComputedStyle(dark as Element).display === "none").toBe(!system);
  document.documentElement.dataset.theme = system ? "light" : "dark";
  onTestFinished(() => {
    delete document.documentElement.dataset.theme;
  });
  expect(getComputedStyle(light as Element).display === "none").toBe(!system);
  expect(getComputedStyle(dark as Element).display === "none").toBe(system);
});

test("the frame's way home is named for the product", async () => {
  const screen = await render(
    branded(
      <AppShell home={<a href="#home" />} switcher={<span>acme</span>} account={<span>alice</span>}>
        Content
      </AppShell>,
    ),
  );
  await expect.element(screen.getByRole("link", { name: "Nightshade" }).first()).toBeVisible();
});

test("signing in says the kit's words and its tagline", async () => {
  const screen = await render(branded(<SignIn onSignIn={async () => null} />));
  await expect
    .element(screen.getByRole("heading", { level: 1, name: "Sign in to Nightshade" }))
    .toBeVisible();
  await expect.element(screen.getByText("Ask, and it is drafted.")).toBeVisible();
});

test("without the kit's words, signing in says portalr's", async () => {
  const screen = await render(
    branded(<SignIn onSignIn={async () => null} />, { ...BRAND, copy: {} }),
  );
  await expect.element(screen.getByRole("heading", { level: 1, name: "Sign in" })).toBeVisible();
});

test("without a kit, the lockup is portalr's", async () => {
  const screen = await render(<Lockup />);
  expect(screen.container.querySelector("img")).toBeNull();
  expect(screen.container.querySelector("svg")).not.toBeNull();
});
