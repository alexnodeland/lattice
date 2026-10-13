import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { playwright } from "@vitest/browser-playwright";
import { defineConfig } from "vitest/config";

// The app's logic and its route tree run without a browser; its own components, such as a
// thread's menu, run in Chromium. The bdd task drives the app itself.
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
          },
        },
      },
    ],
  },
});
