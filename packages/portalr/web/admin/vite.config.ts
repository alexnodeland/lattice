import tailwindcss from "@tailwindcss/vite";
import { tanstackRouter } from "@tanstack/router-plugin/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

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
  // Each route is a chunk of its own, loaded when it is first visited.
  plugins: [tanstackRouter({ ...ROUTES, autoCodeSplitting: true }), react(), tailwindcss()],
  // ui's public files, such as the script that sets the scheme before the first paint.
  publicDir: "../ui/public",
  build: { outDir: "../../src/portalr/static/admin", emptyOutDir: true },
  server: { proxy: { "^/(?!portalr/admin/)": application } },
});
