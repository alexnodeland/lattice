import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { playwright } from "@vitest/browser-playwright";
import { configDefaults, defineConfig } from "vitest/config";
import type { BrowserCommand } from "vitest/node";

// Every component is tested in Chromium twice: with the system's scheme light, and dark. Motion is
// reduced, so a colour is read where it settles rather than mid-transition.
const scheme = (colorScheme: "light" | "dark") => ({
  browser: "chromium" as const,
  name: colorScheme,
  provider: playwright({ contextOptions: { colorScheme, reducedMotion: "reduce" } }),
});

/** Stop asking the browser for reduced motion, or ask again, so a test can see what it stops. */
const reduceMotion: BrowserCommand<[reduce: boolean]> = async ({ page }, reduce) => {
  await page.emulateMedia({ reducedMotion: reduce ? "reduce" : "no-preference" });
};

/**
 * Move the pointer to the page's far corner, off whatever a test renders at the top left, so the
 * last test's click doesn't leave the next one's first control hovered.
 */
const pointerAway: BrowserCommand<[]> = async ({ page }) => {
  const size = page.viewportSize() ?? { width: 414, height: 896 };
  await page.mouse.move(size.width - 1, size.height - 1);
};

/**
 * Put the pointer on what a test marked, holding the main button down if asked, so its `:hover` or
 * `:active` look can be read; or, given "", let go away from there, so letting go clicks nothing.
 */
const pointAt: BrowserCommand<[selector: string, hold?: boolean]> = async (
  { page, frame },
  selector,
  hold = false,
) => {
  if (selector === "") {
    const size = page.viewportSize() ?? { width: 414, height: 896 };
    await page.mouse.move(size.width - 1, size.height - 1);
    await page.mouse.up();
    return;
  }
  const box = await (await frame()).locator(selector).boundingBox();
  if (box === null) throw new Error(`nothing to point at at ${selector}`);
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  if (hold) await page.mouse.down();
};

// The screenshots' baselines are Linux's, made in CI (portalr ADR-0019): they run where CI is.
const screenshots = "src/**/*.screenshot.test.tsx";

// A phone: a finger as the pointer, a narrow window, and the device's scale (portalr ADR-0082).
// Its tests are `*.touch.test.tsx`, run in this instance alone; the rest see a mouse.
const touch = {
  browser: "chromium" as const,
  name: "touch",
  provider: playwright({
    contextOptions: {
      hasTouch: true,
      isMobile: true,
      deviceScaleFactor: 2,
      viewport: { width: 390, height: 844 },
      colorScheme: "light",
      reducedMotion: "reduce",
    },
  }),
};

/** Ask for forced colours, as a high-contrast mode does, or stop asking. */
const forcedColors: BrowserCommand<[active: boolean]> = async ({ page }, active) => {
  await page.emulateMedia({ forcedColors: active ? "active" : "none" });
};

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Streamdown's `rehype-raw`, which portalr never passes it, is built as nothing (portalr ADR-0040),
  // here as in app's and admin's builds, so the tests render what ships; `src/rehype-raw.test.ts`
  // fails if it is dropped. app's and admin's own vitest configs don't alias it: a real raw-HTML
  // feature must remove the alias everywhere, and the stub with it.
  resolve: {
    alias: { "rehype-raw": fileURLToPath(new URL("./src/rehype-raw.ts", import.meta.url)) },
  },
  // Every test's imports are found before the first runs, so a dependency met mid-run doesn't
  // reload the page under the tests.
  optimizeDeps: { entries: ["src/**/*.test.{ts,tsx}"] },
  test: {
    // On 127.0.0.1, not localhost: ui's, app's and admin's servers, started at once, took one
    // port, on ::1 and on 127.0.0.1, and a Chromium reached the other's (portalr ADR-0009).
    api: { host: "127.0.0.1" },
    projects: [
      {
        extends: true,
        test: {
          name: "components",
          include: ["src/**/*.test.{ts,tsx}"],
          setupFiles: ["./src/test/setup.ts"],
          exclude: [
            ...configDefaults.exclude,
            "src/**/*.touch.test.tsx",
            ...(process.env.CI ? [] : [screenshots]),
          ],
          browser: {
            enabled: true,
            headless: true,
            provider: playwright(),
            instances: [scheme("light"), scheme("dark")],
            commands: { forcedColors, pointAt, pointerAway, reduceMotion },
          },
        },
      },
      {
        extends: true,
        test: {
          name: "touch",
          include: ["src/**/*.touch.test.tsx"],
          setupFiles: ["./src/test/setup.ts"],
          browser: {
            enabled: true,
            headless: true,
            provider: playwright(),
            instances: [touch],
            commands: { forcedColors, pointAt, pointerAway, reduceMotion },
          },
        },
      },
      // The Markdown under portalr's Content-Security-Policy: a page built as the UIs are, served
      // with the policy, which Playwright drives from Node (portalr ADR-0043).
      {
        extends: true,
        test: {
          name: "csp",
          include: ["csp/**/*.test.ts"],
          environment: "node",
          globalSetup: ["./csp/serve.ts"],
          // A test renders a page, and some stream a message into it a character at a time, which
          // takes a loaded runner a minute and more: a stream fails sooner if it stops making
          // progress (`csp/markdown.test.ts`'s `STALLED`), and this is the backstop.
          testTimeout: 300_000,
        },
      },
    ],
  },
});
