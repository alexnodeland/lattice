import { defineConfig } from "vitest/config";

// admin's logic and its route tree, without a browser; the bdd task drives admin itself.
export default defineConfig({ test: { include: ["src/**/*.test.ts"] } });
