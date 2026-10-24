import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { playwright } from "@vitest/browser-playwright";
import { defineConfig } from "vitest/config";
import { excalidraw } from "./excalidraw";

// The app's logic and its route tree run without a browser; its own components, such as a
// thread's menu, run in Chromium. The bdd task drives the app itself.
export default defineConfig({
  plugins: [excalidraw("/"), react(), tailwindcss()],
  test: {
    projects: [
      { extends: true, test: { name: "logic", include: ["src/**/*.test.ts"] } },
      {
        extends: true,
        test: {
          name: "components",
          include: ["src/**/*.test.tsx"],
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
    ],
  },
});
