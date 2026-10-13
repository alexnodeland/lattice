import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { playwright } from "@vitest/browser-playwright";
import { defineConfig } from "vitest/config";

// admin's logic and its route tree run without a browser; its own components, such as Home's
// cards, run in Chromium. The bdd task drives admin itself.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  test: {
    projects: [
      { extends: true, test: { name: "logic", include: ["src/**/*.test.ts"] } },
      {
        extends: true,
        test: {
          name: "components",
          include: ["src/**/*.test.tsx"],
          setupFiles: ["./src/test/setup.ts"],
          browser: {
            enabled: true,
            headless: true,
            provider: playwright({ contextOptions: { reducedMotion: "reduce" } }),
            instances: [{ browser: "chromium" }],
            // ui's, app's and admin's tests start their Chromiums at once in CI, where one took longer
            // than Vitest's minute to connect: three minutes covers them (portalr ADR-0009).
            connectTimeout: 180_000,
          },
        },
      },
    ],
  },
});
