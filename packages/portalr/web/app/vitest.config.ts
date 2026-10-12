import { defineConfig } from "vitest/config";

// The app's logic and its route tree, without a browser; the bdd task drives the app itself.
export default defineConfig({ test: { include: ["src/**/*.test.ts"] } });
