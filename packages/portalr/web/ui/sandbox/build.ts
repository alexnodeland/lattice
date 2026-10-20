/**
 * Build the sandbox page mini apps run in (portalr ADR-0051): its script, from
 * `src/sandbox-page.ts`, bundled and minified into the page's one inline script, since the
 * policy it is served under allows inline script and nothing from anywhere. app's build writes
 * it beside the UIs, through `sandboxPage`; the CSP tests serve it on an origin of their own.
 */

import { mkdir, writeFile } from "node:fs/promises";
import { dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { build, type Plugin, type Rolldown } from "vite";

/** What puts markup into a document, which the sandbox's own page must never do. */
const WRITES_MARKUP =
  /\b(innerHTML|outerHTML|insertAdjacentHTML|setHTMLUnsafe|createContextualFragment|write(ln)?)\b/;

const entry = fileURLToPath(new URL("../src/sandbox-page.ts", import.meta.url));

/** The sandbox page, as served: a document whose one script is the sandbox's. */
export async function sandboxHtml(): Promise<string> {
  const built = (await build({
    configFile: false,
    logLevel: "error",
    build: {
      write: false,
      minify: true,
      lib: { entry, formats: ["iife"], name: "sandbox" },
    },
  })) as Rolldown.RolldownOutput[];
  const script = built.flatMap((each) => each.output).find((each) => each.type === "chunk");
  if (script === undefined || /<\/script/i.test(script.code)) {
    throw new Error("the sandbox's script can't be inlined");
  }
  // The sandbox writes nothing it is told, `?host=` above all, into its own page: only the app's
  // frame takes markup, as its `srcdoc`.
  if (WRITES_MARKUP.test(script.code)) {
    throw new Error("the sandbox's script writes markup into its own page");
  }
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Sandbox</title><style>html,body{margin:0;height:100%;background:transparent}</style></head><body><script>${script.code}</script></body></html>\n`;
}

/** Vite's plugin that writes the sandbox page to `file` once the bundle is written. */
export function sandboxPage(file: string): Plugin {
  return {
    name: "portalr-sandbox",
    apply: "build",
    async closeBundle() {
      await mkdir(dirname(file), { recursive: true });
      await writeFile(file, await sandboxHtml());
    },
  };
}
