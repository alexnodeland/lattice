import tailwindcss from "@tailwindcss/vite";
import { tanstackRouter } from "@tanstack/router-plugin/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { ROUTES } from "./routes.config.ts";

// portalr's router serves the built UI at /portalr/app/, from the Python package, whose wheel
// carries it (lattice RFC-0002). In development, Vite's server sends everything else to the
// application, at PORTALR_APP_URL, so the UI shares its origin as it does when served.
const application = process.env.PORTALR_APP_URL ?? "http://localhost:8000";

export default defineConfig({
  base: "/portalr/app/",
  plugins: [tanstackRouter(ROUTES), react(), tailwindcss()],
  build: { outDir: "../../src/portalr/static/app", emptyOutDir: true },
  server: { proxy: { "^/(?!portalr/app/)": application } },
});
