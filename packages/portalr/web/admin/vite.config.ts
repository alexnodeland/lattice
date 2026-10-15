import tailwindcss from "@tailwindcss/vite";
import { tanstackRouter } from "@tanstack/router-plugin/vite";
import react from "@vitejs/plugin-react";
import { defineConfig, type Plugin } from "vite";

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

/**
 * Fails the build where a module that `heavy` matches loads with the entry, rather than with the
 * routes that use it: Recharts is Feedback's and Usage's, so the first page doesn't wait on it.
 */
function lean(heavy: RegExp): Plugin {
  return {
    name: "lean-entry",
    generateBundle(_, bundle) {
      const loaded = new Set<string>();
      const load = (file: string) => {
        const chunk = bundle[file];
        if (loaded.has(file) || chunk?.type !== "chunk") {
          return;
        }
        loaded.add(file);
        chunk.imports.forEach(load);
      };
      for (const [file, chunk] of Object.entries(bundle)) {
        if (chunk.type === "chunk" && chunk.isEntry) {
          load(file);
        }
      }
      const heavyModules = [...loaded].flatMap((file) => {
        const chunk = bundle[file];
        return chunk?.type === "chunk"
          ? Object.keys(chunk.modules).filter((id) => heavy.test(id))
          : [];
      });
      if (heavyModules.length > 0) {
        this.error(
          `the entry loads ${heavyModules.length} modules it shouldn't, such as ${heavyModules[0]}`,
        );
      }
    },
  };
}

export default defineConfig({
  base: "/portalr/admin/",
  // Each route is a chunk of its own, loaded when it is first visited.
  plugins: [
    tanstackRouter({ ...ROUTES, autoCodeSplitting: true }),
    react(),
    tailwindcss(),
    lean(/[\\/]node_modules[\\/](recharts|d3-[a-z]+)[\\/]/),
  ],
  // ui's public files, such as the script that sets the scheme before the first paint.
  publicDir: "../ui/public",
  build: { outDir: "../../src/portalr/static/admin", emptyOutDir: true },
  server: { proxy: { "^/(?!portalr/admin/)": application } },
});
