import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// portalr's router serves the built UI at /portalr/admin/, from the Python package, whose wheel
// carries it (lattice RFC-0002).
export default defineConfig({
  base: "/portalr/admin/",
  plugins: [react(), tailwindcss()],
  // ui's public files, such as the script that sets the scheme before the first paint.
  publicDir: "../ui/public",
  build: { outDir: "../../src/portalr/static/admin", emptyOutDir: true },
});
