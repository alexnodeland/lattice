import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { playwright } from "@vitest/browser-playwright";
import { configDefaults, defineConfig } from "vitest/config";
import type { BrowserCommand } from "vitest/node";

// Every component is tested in Chromium twice: with the system's scheme light, and dark.
const scheme = (colorScheme: "light" | "dark") => ({
  browser: "chromium" as const,
  name: colorScheme,
  provider: playwright({ contextOptions: { colorScheme } }),
});

/** Ask the browser for reduced motion, or stop asking, so a test can see what it stops. */
const reduceMotion: BrowserCommand<[reduce: boolean]> = async ({ page }, reduce) => {
  await page.emulateMedia({ reducedMotion: reduce ? "reduce" : "no-preference" });
};

// The screenshots' baselines are Linux's, made in CI (portalr ADR-0019): they run where CI is.
const screenshots = "src/**/*.screenshot.test.tsx";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  test: {
    setupFiles: ["./src/test/setup.ts"],
    exclude: [...configDefaults.exclude, ...(process.env.CI ? [] : [screenshots])],
    browser: {
      enabled: true,
      headless: true,
      provider: playwright(),
      instances: [scheme("light"), scheme("dark")],
      commands: { reduceMotion },
    },
  },
});
