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

// The screenshots' baselines are Linux's, made in CI (portalr ADR-0019): they run where CI is.
const screenshots = "src/**/*.screenshot.test.tsx";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Every test's imports are found before the first runs, so a dependency met mid-run doesn't
  // reload the page under the tests.
  optimizeDeps: { entries: ["src/**/*.test.{ts,tsx}"] },
  test: {
    setupFiles: ["./src/test/setup.ts"],
    exclude: [...configDefaults.exclude, ...(process.env.CI ? [] : [screenshots])],
    // On 127.0.0.1, not localhost: ui's, app's and admin's servers, started at once, took one
    // port, on ::1 and on 127.0.0.1, and a Chromium reached the other's (portalr ADR-0009).
    api: { host: "127.0.0.1" },
    browser: {
      enabled: true,
      headless: true,
      provider: playwright(),
      instances: [scheme("light"), scheme("dark")],
      commands: { pointerAway, reduceMotion },
    },
  },
});
