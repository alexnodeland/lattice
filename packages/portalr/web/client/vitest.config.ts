import { defineConfig } from "vitest/config";

// `unit` runs everywhere; `api` runs against docplan and oncall, from the `api` task, which
// starts them (scripts/api).
export default defineConfig({
  test: {
    projects: [
      { test: { name: "unit", include: ["src/**/*.test.ts"] } },
      { test: { name: "api", include: ["api/**/*.test.ts"], testTimeout: 60_000 } },
    ],
  },
});
