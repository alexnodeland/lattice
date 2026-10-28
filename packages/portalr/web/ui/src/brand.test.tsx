import type { ReactNode } from "react";
import { expect, onTestFinished, test } from "vitest";
import { page } from "vitest/browser";
import { render } from "vitest-browser-react";
import { type Brand, BrandContext, pageTitle } from "./brand";
import { Lockup } from "./marks";
import { NewVersion } from "./new-version";
import { Plain } from "./plain";
import { RailShell } from "./rail-shell";
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

test("the frame's way home is named for the product: on the rail, and in a phone's drawer", async () => {
  const frame = branded(
    <RailShell home={<a href="#home" />} switcher={<span>acme</span>} account={<span>alice</span>}>
      Content
    </RailShell>,
  );
  await page.viewport(1280, 800);
  onTestFinished(() => page.viewport(414, 896));
  let screen = await render(frame);
  await expect.element(screen.getByRole("link", { name: "Nightshade" }).first()).toBeVisible();
  await screen.unmount();
  // A phone's bar leaves the mark out for the switcher's room (portalr ADR-0085): it is in the drawer.
  await page.viewport(390, 800);
  screen = await render(frame);
  expect(
    screen
      .getByRole("link", { name: "Nightshade" })
      .elements()
      .filter((link) => link.checkVisibility()),
  ).toHaveLength(0);
  await screen.getByRole("button", { name: "Menu" }).click();
  await expect
    .element(page.getByRole("dialog").getByRole("link", { name: "Nightshade" }))
    .toBeVisible();
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

const LONG = "Supercalifragilisticexpialidocious-and-a-great-deal-more-than-that";
const EMOJI =
  "Nightshade \u{1F319}\u{1F319}\u{1F319} \u{1F468}\u200d\u{1F469}\u200d\u{1F467} for everyone, every day";

/** The marks a person sees: those drawn, with every box around them drawn too. */
const shown = (within: ParentNode) =>
  [...within.querySelectorAll("img")].filter((mark) => mark.checkVisibility());

for (const scheme of ["light", "dark"] as const) {
  test(`in the frame, wide and ${scheme}, the kit's mark is drawn once`, async () => {
    await page.viewport(1280, 900);
    onTestFinished(() => page.viewport(414, 896));
    document.documentElement.dataset.theme = scheme;
    onTestFinished(() => {
      delete document.documentElement.dataset.theme;
    });
    const screen = await render(
      branded(
        <RailShell home={<a href="#home" />} switcher={<span>acme</span>} account={<span>a</span>}>
          Content
        </RailShell>,
      ),
    );
    const marks = shown(screen.container);
    expect(marks).toHaveLength(1);
    expect(marks[0]?.getAttribute("src")).toContain(`mark-${scheme}.svg`);
  });
}

test("a plain page's way home is named for the product, as it shows", async () => {
  const screen = await render(
    branded(<Plain ui="admin" home={<a href="#home" />} title="Tenants" />),
  );
  await expect.element(screen.getByRole("link", { name: "Nightshade admin" })).toBeVisible();
});

test("a new version is offered by the product's name", async () => {
  const screen = await render(branded(<NewVersion ui="app" onDismiss={() => undefined} />));
  await expect
    .element(screen.getByText("A new version of Nightshade is ready.", { exact: false }))
    .toBeVisible();
});

test("a page's title is what it is, then the UI's name: the kit's, or portalr's", () => {
  expect(pageTitle(BRAND, "admin", "Runs", "acme")).toBe("Runs · acme · Nightshade admin");
  expect(pageTitle(null, "app", "Runs")).toBe("Runs · portalr");
  expect(pageTitle(undefined, "admin")).toBe("portalr admin");
});

for (const name of [LONG, EMOJI]) {
  const long = { ...BRAND, identity: { product: name, app: name, admin: name } };
  test(`a long name (${name.slice(0, 12)}…) fits the rail and the drawer, and is said whole`, async () => {
    for (const [width, open] of [
      [1280, false],
      [390, true],
    ] as const) {
      await page.viewport(width, 900);
      onTestFinished(() => page.viewport(414, 896));
      const screen = await render(
        branded(
          <RailShell
            home={<a href="#home" />}
            switcher={<span>acme</span>}
            account={<span>a</span>}
          >
            Content
          </RailShell>,
          long,
        ),
      );
      if (open) {
        await screen.getByRole("button", { name: "Menu" }).click();
      }
      const home = [...document.querySelectorAll(`a[title="${name}"]`)].at(-1) as Element;
      expect(home.getAttribute("aria-label")).toBe(name);
      const box = home.getBoundingClientRect();
      const within = (home.closest("header, [role='dialog']") as Element).getBoundingClientRect();
      expect(box.right).toBeLessThanOrEqual(within.right + 0.5);
      if (open) {
        await expect.element(page.getByRole("button", { name: "Close" })).toBeInViewport();
      }
      await screen.unmount();
    }
  });

  test(`a long name (${name.slice(0, 12)}…) fits a plain page and signing in`, async () => {
    await page.viewport(390, 900);
    onTestFinished(() => page.viewport(414, 896));
    for (const view of [
      <Plain key="plain" home={<a href="#home" />} title="Tenants" />,
      <SignIn key="sign-in" ui="admin" onSignIn={async () => null} />,
    ]) {
      const screen = await render(branded(view, long));
      const lockup = screen.container.querySelector(".truncate");
      expect(lockup?.textContent).toBe(name);
      expect(lockup?.getAttribute("title")).toBe(name);
      expect(lockup?.getBoundingClientRect().right).toBeLessThanOrEqual(window.innerWidth);
      await screen.unmount();
    }
  });
}

test("admin's sign-in is named for admin, with the kit's words", async () => {
  const screen = await render(branded(<SignIn ui="admin" onSignIn={async () => null} />));
  await expect.element(screen.getByText("Nightshade admin")).toBeVisible();
  await expect
    .element(screen.getByRole("heading", { level: 1, name: "Sign in to Nightshade" }))
    .toBeVisible();
});

test("a right-to-left name is set in its own direction", async () => {
  const screen = await render(
    branded(<Lockup />, { ...BRAND, identity: { product: "ليل", app: "ليل", admin: "ليل" } }),
  );
  expect(screen.getByText("ليل").element().getAttribute("dir")).toBe("auto");
});
