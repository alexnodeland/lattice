// The worker's page, and Excalidraw's faces beside it, which its exports embed. Xiaolai, the CJK
// face, is left out unless XIAOLAI is 1, until its licence is confirmed (lattice#679): Noto CJK,
// the image's system face, draws CJK meanwhile (stackr ADR-0049).

import { cpSync, readdirSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { notices, readPolicy } from "@portalr/notices";
import { defineConfig, type Plugin } from "vite";

const fonts = join(
  dirname(createRequire(import.meta.url).resolve("@excalidraw/excalidraw")),
  "fonts",
);

function faces(): Plugin {
  return {
    name: "excalidraw-faces",
    apply: "build",
    writeBundle(options) {
      const out = join(options.dir ?? "dist/page", "fonts");
      for (const face of readdirSync(fonts)) {
        if (face === "Xiaolai" && process.env.XIAOLAI !== "1") continue;
        cpSync(join(fonts, face), join(out, face), { recursive: true });
      }
    },
  };
}

export default defineConfig({
  base: "./",
  plugins: [
    faces(),
    notices({
      ui: "diagrams worker",
      policy: readPolicy(new URL("policy.json", import.meta.url)),
      preface: (_, count) => [
        "Third-party notices for the JavaScript in stackr's diagrams worker's page",
        "",
        `The ${count} packages below are bundled into the page. Their own licences and notices`,
        "follow, as they ship them. The typefaces' are in FONTS.txt, beside this file.",
      ],
    }),
  ],
  build: {
    outDir: "dist/page",
    emptyOutDir: true,
    target: "es2023",
    chunkSizeWarningLimit: 4096,
  },
});
