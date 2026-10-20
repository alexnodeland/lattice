import { fileURLToPath } from "node:url";
import { notices, readPolicy } from "@portalr/notices";
import { sandboxPage } from "@portalr/ui/sandbox";
import tailwindcss from "@tailwindcss/vite";
import { tanstackRouter } from "@tanstack/router-plugin/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

/**
 * Where the app's routes are, and the route tree TanStack Router generates from them, which is
 * committed: the plugin writes it, and `src/routes.test.ts` fails if it drifts. Its own notice
 * heads it, in place of a header that turns the typecheck off for the file, which passes it.
 */
export const ROUTES = {
  target: "react" as const,
  routesDirectory: "./src/routes",
  generatedRouteTree: "./src/routeTree.gen.ts",
  routeTreeFileHeader: [],
};

// portalr's router serves the built UI at /portalr/app/, from the Python package, whose wheel
// carries it (lattice RFC-0002). In development, Vite's server sends everything else to the
// application, at PORTALR_APP_URL, so the UI shares its origin as it does when served.
const application = process.env.PORTALR_APP_URL ?? "http://localhost:8000";

export default defineConfig({
  base: "/portalr/app/",
  // Each route is a chunk of its own, loaded when it is first visited.
  plugins: [
    tanstackRouter({ ...ROUTES, autoCodeSplitting: true }),
    react(),
    tailwindcss(),
    // The licences of the packages bundled, beside the UI (portalr ADR-0033).
    notices({ ui: "app", policy: readPolicy(new URL("../notices/policy.json", import.meta.url)) }),
    // The page mini apps run in, served on the apps' origin alone (portalr ADR-0051).
    sandboxPage(
      fileURLToPath(new URL("../../src/portalr/static/sandbox/index.html", import.meta.url)),
    ),
  ],
  // ui's public files, such as the script that sets the scheme before the first paint.
  publicDir: "../ui/public",
  // The manifest says which chunk each import is, which the size check reads (portalr ADR-0044).
  build: { outDir: "../../src/portalr/static/app", emptyOutDir: true, manifest: true },
  server: { proxy: { "^/(?!portalr/app/)": application } },
});
