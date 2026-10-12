import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { playwright } from "@vitest/browser-playwright";
import { defineConfig } from "vitest/config";

// Every component is tested in Chromium twice: with the system's scheme light, and dark.
const scheme = (colorScheme: "light" | "dark") => ({
  browser: "chromium" as const,
  name: colorScheme,
  provider: playwright({ contextOptions: { colorScheme } }),
});

export default defineConfig({
  plugins: [react(), tailwindcss()],
  test: {
    setupFiles: ["./src/test/setup.ts"],
    browser: {
      enabled: true,
      headless: true,
      provider: playwright(),
      instances: [scheme("light"), scheme("dark")],
    },
  },
});
