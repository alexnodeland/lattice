/**
 * Build the CSP tests' page, and serve it with the Content-Security-Policy both UIs share, which
 * `policy.txt` holds and a portalr test holds to the router's own; serve mini apps' sandbox page
 * on an origin of its own, a second port, under the app's policy (`app-policy.txt`), with the
 * headers `SandboxOrigin` sends (portalr ADR-0051); and serve an editor's shim, as artifactr
 * writes it (`shim-script.js`, held to the source by a portalr test), before a stand-in build, on
 * a third port, under the shim's policy (native files ADR-0010).
 *
 * The page is reached at two origins, `127.0.0.1` and `localhost`, which Chromium keeps apart, as
 * a portal at its loopback address and its tailnet name is two origins (portalr ADR-0084): the
 * sandbox and the shim are framed by both, the sandbox is reached beside each on its own port, and
 * the page's `frame-src` is the union of what each origin frames.
 */

import { execFile } from "node:child_process";
import { createHash } from "node:crypto";
import { readFile, rm } from "node:fs/promises";
import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import type { AddressInfo } from "node:net";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import { preview } from "vite";
import type { TestProject } from "vitest/node";

declare module "vitest" {
  export interface ProvidedContext {
    /** Where the page is served, on 127.0.0.1. */
    harness: string;
    /** The apps' origin, where the sandbox page is served, beside the page on 127.0.0.1. */
    apps: string;
    /** The same page and sandbox reached at `localhost`: another origin, on the same ports. */
    localhost: { harness: string; apps: string };
    /** The editor's origin, where the shim is served before a stand-in build, on 127.0.0.1. */
    editor: string;
  }
}

const ui = fileURLToPath(new URL("..", import.meta.url));
const outDir = fileURLToPath(new URL("../node_modules/.csp", import.meta.url));

/** The build the shim frames: it says it is ready to its parent, on its own origin, as asked. */
const BUILD_SCRIPT =
  'if (location.search === "?host=parent") parent.postMessage({ type: "probe:ready", version: "1" }, location.origin);';
const SHIM_STYLE = "html, body, iframe { margin: 0; border: 0; width: 100%; height: 100%; }";

const hash = (text: string) => `'sha256-${createHash("sha256").update(text).digest("base64")}'`;

/** A server on 127.0.0.1, answering as `answer` does; its origin at 127.0.0.1 and at localhost. */
async function serving(answer: (request: IncomingMessage, response: ServerResponse) => void) {
  const server = createServer(answer);
  await new Promise<void>((listening) => server.listen(0, "127.0.0.1", listening));
  const { port } = server.address() as AddressInfo;
  return { server, origin: `http://127.0.0.1:${port}`, alias: `http://localhost:${port}` };
}

export default async function serve(project: TestProject) {
  // A build of its own, in a process of its own: a production build in this one would share it
  // with the server that transforms the component tests as they run.
  await promisify(execFile)(
    "bun",
    ["x", "--bun", "--no-install", "vite", "build", "--config", "csp/vite.config.ts"],
    // As app's and admin's builds are, for production: vitest's own NODE_ENV, test, would build
    // packages' development code, such as Excalidraw's (portalr ADR-0072).
    { cwd: ui, env: { ...process.env, NODE_ENV: "production" } },
  );
  const sandbox = await readFile(`${outDir}/sandbox/index.html`);
  const appPolicy = (await readFile(new URL("app-policy.txt", import.meta.url), "utf8")).trim();
  const shimScript = (await readFile(new URL("shim-script.js", import.meta.url), "utf8")).trim();
  // The portal's origins, known once the page's server is up: the sandbox and the shim are
  // framed by both, as `sandbox_policy` and `shim_policy` name them all.
  let portals = "";
  const apps = await serving((request, response) => {
    const found = new URL(request.url ?? "/", "http://apps").pathname === "/";
    response.writeHead(found ? 200 : 404, {
      "Content-Type": "text/html",
      "Content-Security-Policy": `${appPolicy}; frame-ancestors ${portals}`,
      "X-Content-Type-Options": "nosniff",
      "Referrer-Policy": "no-referrer",
      "X-DNS-Prefetch-Control": "off",
    });
    response.end(found ? sandbox : "Nothing is served here.");
  });
  const editor = await serving((request, response) => {
    const { pathname } = new URL(request.url ?? "/", "http://editor");
    const headers = { "Content-Type": "text/html", "X-Content-Type-Options": "nosniff" };
    if (pathname === "/.lattice/shim.html") {
      // As `shim_page` writes it, for a build with a `?host=parent` bridge, told both portals.
      const page = `<!DOCTYPE html><html lang="en" data-app="probe" data-portals="${portals}" data-surface="parent" data-methods=""><head><meta charset="utf-8"><title>Probe</title><style>${SHIM_STYLE}</style></head><body><iframe title="Probe"></iframe><script>${shimScript}</script></body></html>`;
      const policy = `default-src 'none'; script-src ${hash(shimScript)}; style-src ${hash(SHIM_STYLE)}; frame-src 'self'; frame-ancestors ${portals}; base-uri 'none'; form-action 'none'`;
      response.writeHead(200, { ...headers, "Content-Security-Policy": policy });
      response.end(page);
    } else if (pathname === "/") {
      // The build, as `editor_policy` serves it: framed by its own origin and the portals.
      const policy = `default-src 'none'; script-src ${hash(BUILD_SCRIPT)}; frame-ancestors 'self' ${portals}`;
      response.writeHead(200, { ...headers, "Content-Security-Policy": policy });
      response.end(`<!DOCTYPE html><title>Build</title><script>${BUILD_SCRIPT}</script>`);
    } else {
      response.writeHead(404, headers);
      response.end("Nothing is served here.");
    }
  });
  const policy = (await readFile(new URL("policy.txt", import.meta.url), "utf8")).trim();
  const server = await preview({
    configFile: false,
    root: fileURLToPath(new URL(".", import.meta.url)),
    logLevel: "error",
    build: { outDir },
    preview: {
      host: "127.0.0.1",
      port: 0,
      headers: {
        // As `Site(apps=..., editors=..., aliases=...)` adds it: the apps' and the editor's origins
        // beside each portal origin, the union, each once (portalr ADR-0084).
        "Content-Security-Policy": `${policy}; frame-src ${apps.origin} ${editor.origin} ${apps.alias} ${editor.alias}`,
        "X-Content-Type-Options": "nosniff",
      },
    },
  });
  const [url] = server.resolvedUrls?.local ?? [];
  if (!url) {
    throw new Error("the CSP tests' page has no address");
  }
  const { port } = new URL(url);
  portals = `http://127.0.0.1:${port} http://localhost:${port}`;
  project.provide("harness", url);
  project.provide("apps", apps.origin);
  project.provide("localhost", { harness: `http://localhost:${port}/`, apps: apps.alias });
  project.provide("editor", editor.origin);
  return async () => {
    apps.server.close();
    editor.server.close();
    await server.close();
    await rm(outDir, { recursive: true, force: true });
  };
}
