import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// portalr's router serves the built UI at /portalr/admin/, from the Python package, whose wheel
// carries it (lattice RFC-0002).
export default defineConfig({
  base: "/portalr/admin/",
  plugins: [react()],
  build: { outDir: "../../src/portalr/static/admin", emptyOutDir: true },
});
