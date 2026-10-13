import { defineConfig } from "@playwright/test";
import { defineBddConfig } from "playwright-bdd";

// admin's scenarios, one feature per area (lattice RFC-0002), against the test application
// that scripts/bdd starts and names in PORTALR_APP_URL.
const testDir = defineBddConfig({ features: "bdd/features/*.feature", steps: "bdd/steps/*.ts" });

export default defineConfig({
  testDir,
  forbidOnly: true,
  reporter: [["list"]],
  use: {
    baseURL: new URL("/portalr/admin/", process.env.PORTALR_APP_URL ?? "http://localhost:8000")
      .href,
    browserName: "chromium",
    trace: "retain-on-failure",
  },
});
