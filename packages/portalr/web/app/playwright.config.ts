import { defineConfig } from "@playwright/test";
import { defineBddConfig } from "playwright-bdd";

// The app's scenarios, one feature per area (lattice RFC-0002), against the test application
// that scripts/bdd starts and names in PORTALR_APP_URL; or, with PORTALR_FEATURES naming
// bdd/generated/*.feature, against a generated application (scripts/generated).
const testDir = defineBddConfig({
  features: process.env.PORTALR_FEATURES ?? "bdd/features/*.feature",
  steps: "bdd/steps/*.ts",
});

export default defineConfig({
  testDir,
  forbidOnly: true,
  reporter: [["list"]],
  use: {
    baseURL: new URL("/portalr/app/", process.env.PORTALR_APP_URL ?? "http://localhost:8000").href,
    browserName: "chromium",
    trace: "retain-on-failure",
  },
});
