import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { playwright } from "@vitest/browser-playwright";
import { configDefaults, defineConfig } from "vitest/config";
import { excalidraw } from "./excalidraw";

// The app's logic and its route tree run without a browser; its own components, such as a
// thread's menu, run in Chromium. The bdd task drives the app itself.
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
  plugins: [excalidraw("/"), react(), tailwindcss()],
  // Found only as the canvas's tests import them, they'd be optimised mid-run, and Vite would
  // reload the browser under the tests then running: a file's tester never comes ready (#699).
  optimizeDeps: { include: ["@excalidraw/excalidraw", "axe-core", "react-dom/client"] },
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
      // A project per scheme, so each keeps a failing test's Playwright trace in a folder of its
      // own: two schemes' traces written to one collide.
      ...(["light", "dark"] as const).map((scheme) => ({
        extends: true,
        test: {
          name: `phone-${scheme}`,
          include: ["src/**/*.touch.test.tsx"],
          setupFiles: ["./src/test/setup.ts", "./src/test/phone.ts"],
          api: { host: "127.0.0.1" },
          browser: {
            enabled: true,
            headless: true,
            provider: playwright(),
            instances: [phone(scheme)],
            // Its DOM and its actions, without screenshots, which a page that stalls can't
            // take: what CI uploads as app-traces.
            trace: {
              mode: "retain-on-failure" as const,
              tracesDir: `.vitest/traces/${scheme}`,
              screenshots: false,
            },
          },
        },
      })),
    ],
  },
});
