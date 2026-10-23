import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { absent, RAW_HTML } from "../bundle-checks";
import { sandboxPage } from "../sandbox/build";

const outDir = "../node_modules/.csp";

// The CSP tests' page, built with the React and Tailwind plugins and the public files app and admin
// build with, into node_modules, since it is never shipped (portalr ADR-0043); and mini apps'
// sandbox page beside it, as app's build writes it, which the tests serve on an origin of its own
// (portalr ADR-0051).
export default defineConfig({
  root: import.meta.dirname,
  // Streamdown's `rehype-raw`, which portalr never passes it, is built as nothing (portalr ADR-0040).
  resolve: {
    alias: { "rehype-raw": fileURLToPath(new URL("../src/rehype-raw.ts", import.meta.url)) },
  },
  plugins: [
    react(),
    tailwindcss(),
    absent(RAW_HTML),
    sandboxPage(fileURLToPath(new URL(`${outDir}/sandbox/index.html`, import.meta.url))),
  ],
  publicDir: "../public",
  // Its one chunk is larger than Vite's warning: it is never shipped, so only errors are said.
  logLevel: "error",
  build: { outDir, emptyOutDir: true },
});
