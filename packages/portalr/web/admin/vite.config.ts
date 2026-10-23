import { fileURLToPath } from "node:url";
import { notices, readPolicy } from "@portalr/notices";
import tailwindcss from "@tailwindcss/vite";
import { tanstackRouter } from "@tanstack/router-plugin/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { absent, lean } from "../ui/bundle-checks";

/**
 * Where admin's routes are, and the route tree TanStack Router generates from them, which is
 * committed: the plugin writes it, and `src/routes.test.ts` fails if it drifts, as app's does.
 */
export const ROUTES = {
  target: "react" as const,
  routesDirectory: "./src/routes",
  generatedRouteTree: "./src/routeTree.gen.ts",
  routeTreeFileHeader: [],
};

// portalr's router serves the built UI at /portalr/admin/, from the Python package, whose wheel
// carries it (lattice RFC-0002). In development, Vite's server sends everything else to the
// application, at PORTALR_APP_URL, so the UI shares its origin as it does when served.
const application = process.env.PORTALR_APP_URL ?? "http://localhost:8000";

export default defineConfig({
  base: "/portalr/admin/",
  // Streamdown's `rehype-raw`, which portalr never passes it, is built as nothing (portalr ADR-0040).
  resolve: {
    alias: { "rehype-raw": fileURLToPath(new URL("../ui/src/rehype-raw.ts", import.meta.url)) },
  },
  // Each route is a chunk of its own, loaded when it is first visited.
  plugins: [
    tanstackRouter({ ...ROUTES, autoCodeSplitting: true }),
    react(),
    tailwindcss(),
    lean(/[\\/]node_modules[\\/](recharts|d3-[a-z]+)[\\/]/),
    absent(
      /[\\/]node_modules[\\/](rehype-raw|parse5|hast-util-raw|hast-util-from-parse5|hast-util-to-parse5)[\\/]/,
    ),
    // The licences of the packages bundled, beside the UI (portalr ADR-0033).
    notices({
      ui: "admin",
      policy: readPolicy(new URL("../notices/policy.json", import.meta.url)),
    }),
  ],
  // ui's public files, such as the script that sets the scheme before the first paint.
  publicDir: "../ui/public",
  // The manifest says which chunk each import is, which the size check reads (portalr ADR-0044).
  build: { outDir: "../../src/portalr/static/admin", emptyOutDir: true, manifest: true },
  server: { proxy: { "^/(?!portalr/admin/)": application } },
});
