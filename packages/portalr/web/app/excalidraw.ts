/**
 * Excalidraw in the app's build, as the canvas add-on needs it and nothing more (portalr
 * ADR-0072, artifactr ADR-0088):
 *
 * - font subsetting is the diagrams worker's: its chunks, 741 kB with their WebAssembly, are
 *   built as a module that refuses, and an export from the canvas embeds whole faces instead;
 * - Mermaid runs only in the worker, so its converter is built the same way, and so is the
 *   resizing of an image put on the canvas, which takes no image yet;
 * - the locales but English are built as nothing: the canvas speaks the app's English;
 * - no face is fetched from esm.sh: the fallback Excalidraw names is the app's own copy, and the
 *   build fails if any file it writes names esm.sh;
 * - the faces but Xiaolai are copied beside the app, at `excalidraw/fonts/`, which
 *   `EXCALIDRAW_ASSET_PATH` names. Xiaolai, the CJK face, waits for its licence (lattice#679):
 *   it isn't registered, so nothing asks for it, and browsers draw CJK with a face of their own.
 */

import { cpSync, readdirSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import type { Plugin } from "vite";

/** Where the app serves Excalidraw's faces, under its base. */
const ASSETS = "excalidraw/";

/**
 * What the canvas's modules are marked with, so none is shared with the rest of the app: a module
 * both import would be split into a chunk of its own, which the first load would then fetch, and
 * every route's chunk would name. React is the one module shared, since there must be one React.
 */
const OWN = "?canvas";
const SHARED = /^(react|react-dom|scheduler)([\\/]|$)/;

const REFUSED = "\0excalidraw-refused";
const EMPTY = "\0excalidraw-empty";
const IN_EXCALIDRAW = /[\\/]@excalidraw[\\/]excalidraw[\\/]dist[\\/]/;
/**
 * What the canvas never runs: subsetting, Mermaid's converter, and the resizing of an image put on
 * it, pica's and image-blob-reduce's, as the canvas takes no image yet.
 */
const NEVER =
  /(?:^|[\\/])subset-(?:shared|worker)\.chunk\.js$|^@excalidraw\/mermaid-to-excalidraw$|^pica$|^image-blob-reduce$/;
/** A locale but English. */
const LOCALE = /(?:^|[\\/])locales[\\/](?!en-)[a-z]{2}-[A-Z]{2}-[A-Z0-9]+\.js$/;
/**
 * esbuild's stand-in for `require`, which Excalidraw's build keeps and a browser never calls: the
 * bundler would put its own in the runtime every chunk shares, and so in the first load. It is
 * kept as what it does in a browser, throw.
 */
const REQUIRE =
  /var (\w+)=\((\w+)=>typeof require<"u"\?require:typeof Proxy<"u"\?new Proxy\(\2,\{get:\((\w+),(\w+)\)=>\(typeof require<"u"\?require:\3\)\[\4\]\}\):\2\)\(function\((\w+)\)\{if\(typeof require<"u"\)return require\.apply\(this,arguments\);throw/g;

/** The name Excalidraw gives Xiaolai, its CJK face, in a constant of its own. */
const XIAOLAI = /[,{\s](\w+)="Xiaolai"/;

/** The fallback Excalidraw fetches faces from, a template literal naming esm.sh. */
const FALLBACK = /("ASSETS_FALLBACK_URL",\s*)`https:\/\/esm\.sh\/[\s\S]{0,300}?\/dist\/prod\/`/;

function fonts(): string {
  const entry = createRequire(import.meta.url).resolve("@excalidraw/excalidraw");
  return join(dirname(entry), "fonts");
}

export function excalidraw(base: string): Plugin {
  return {
    name: "excalidraw",
    enforce: "pre",
    async resolveId(source, importer, options) {
      if (importer === undefined) return null;
      const owned = importer.endsWith(OWN) || IN_EXCALIDRAW.test(importer);
      if (!owned) return null;
      if (IN_EXCALIDRAW.test(importer) && NEVER.test(source)) return REFUSED;
      if (IN_EXCALIDRAW.test(importer) && LOCALE.test(source)) return EMPTY;
      if (SHARED.test(source) || source.startsWith("\0")) return null;
      const resolved = await this.resolve(source, importer, { ...options, skipSelf: true });
      if (resolved === null || resolved.external || resolved.id.startsWith("\0")) return resolved;
      if (/[\\/]node_modules[\\/](react|react-dom|scheduler)[\\/]/.test(resolved.id)) {
        return resolved;
      }
      const id = resolved.id.split("?")[0] ?? resolved.id;
      return /\.(css|json)$/.test(id) ? resolved : { ...resolved, id: `${id}${OWN}` };
    },
    load(id) {
      if (id === REFUSED) {
        return 'throw new Error("not in portalr: the diagrams worker draws this (artifactr ADR-0088)");';
      }
      if (id === EMPTY) return "export default {};";
      return null;
    },
    transform(code, id) {
      if (!IN_EXCALIDRAW.test(id)) return null;
      let changed = code.replace(REQUIRE, "var $1=(function($5){throw");
      // Xiaolai's faces registered, as `register(XIAOLAI, ...faces)` among the others: not.
      const xiaolai = XIAOLAI.exec(changed)?.[1];
      if (xiaolai !== undefined && changed.includes("._initialized=!0")) {
        const registered = new RegExp(`\\w+\\(${xiaolai},\\.\\.\\.\\w+\\),`);
        if (!registered.test(changed)) {
          this.error("Excalidraw's faces aren't registered where they were: check Xiaolai's");
        }
        changed = changed.replace(registered, "");
      }
      if (changed.includes('"ASSETS_FALLBACK_URL"')) {
        if (!FALLBACK.test(changed)) {
          this.error("Excalidraw's face fallback isn't where it was: check it still names esm.sh");
        }
        changed = changed.replace(
          FALLBACK,
          // Excalidraw makes each face's address from it as a base, which must be whole.
          `$1new URL(${JSON.stringify(base + ASSETS)}, location.origin).href`,
        );
      }
      return changed === code ? null : changed;
    },
    generateBundle(_, bundle) {
      const naming = Object.entries(bundle)
        .filter(([, file]) =>
          (file.type === "chunk" ? file.code : String(file.source)).includes("esm.sh"),
        )
        .map(([name]) => name);
      if (naming.length > 0) {
        this.error(`these name esm.sh, which the app never loads from: ${naming.join(", ")}`);
      }
    },
    writeBundle(options) {
      const out = join(options.dir ?? "dist", ASSETS, "fonts");
      for (const face of readdirSync(fonts())) {
        if (face !== "Xiaolai") cpSync(join(fonts(), face), join(out, face), { recursive: true });
      }
    },
  };
}
