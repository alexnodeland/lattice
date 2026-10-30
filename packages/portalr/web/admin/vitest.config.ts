import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { playwright } from "@vitest/browser-playwright";
import { configDefaults, defineConfig } from "vitest/config";

// admin's logic and its route tree run without a browser; its own components, such as Home's
// cards, run in Chromium. The bdd task drives admin itself.
// A phone: a finger as the pointer, a narrow window, the device's scale, in each scheme (portalr
// ADR-0082). Its tests are `*.touch.test.tsx`, run in this project alone; the rest see a mouse.
const phone = (colorScheme: "light" | "dark") => ({
  browser: "chromium" as const,
  name: colorScheme,
  provider: playwright({
    contextOptions: {
      colorScheme,
      hasTouch: true,
      isMobile: true,
      deviceScaleFactor: 2,
      viewport: { width: 390, height: 844 },
      reducedMotion: "reduce",
    },
  }),
});

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
          exclude: [...configDefaults.exclude, "src/**/*.touch.test.tsx"],
          setupFiles: ["./src/test/setup.ts"],
          // On 127.0.0.1, not localhost: ui's, app's and admin's servers, started at once, took one
          // port, on ::1 and on 127.0.0.1, and a Chromium reached the other's (portalr ADR-0009).
          api: { host: "127.0.0.1" },
          browser: {
            enabled: true,
            headless: true,
            provider: playwright({ contextOptions: { reducedMotion: "reduce" } }),
            instances: [{ browser: "chromium" }],
          },
        },
      },
      {
        extends: true,
        test: {
          name: "phone",
          include: ["src/**/*.touch.test.tsx"],
          setupFiles: ["./src/test/setup.ts", "../ui/src/test/phone.ts"],
          api: { host: "127.0.0.1" },
          browser: {
            enabled: true,
            headless: true,
            provider: playwright(),
            instances: [phone("light"), phone("dark")],
          },
        },
      },
    ],
  },
});
