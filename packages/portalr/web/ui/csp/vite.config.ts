import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The CSP tests' page, built with the React and Tailwind plugins and the public files app and admin
// build with, into node_modules, since it is never shipped (portalr ADR-0043).
export default defineConfig({
  root: import.meta.dirname,
  plugins: [react(), tailwindcss()],
  publicDir: "../public",
  // Its one chunk is larger than Vite's warning: it is never shipped, so only errors are said.
  logLevel: "error",
  build: { outDir: "../node_modules/.csp", emptyOutDir: true },
});
