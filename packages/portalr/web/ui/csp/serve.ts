/**
 * Build the CSP tests' page, and serve it with the Content-Security-Policy both UIs share, which
 * `policy.txt` holds and a portalr test holds to the router's own; and serve mini apps' sandbox
 * page on an origin of its own, a second port, under the app's policy (`app-policy.txt`), framed
 * by the page alone, with the headers `SandboxOrigin` sends (portalr ADR-0051).
 */

import { execFile } from "node:child_process";
import { readFile, rm } from "node:fs/promises";
import { createServer } from "node:http";
import type { AddressInfo } from "node:net";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import { preview } from "vite";
import type { TestProject } from "vitest/node";

declare module "vitest" {
  export interface ProvidedContext {
    /** Where the page is served. */
    harness: string;
    /** The apps' origin, where the sandbox page is served. */
    apps: string;
  }
}

const ui = fileURLToPath(new URL("..", import.meta.url));
const outDir = fileURLToPath(new URL("../node_modules/.csp", import.meta.url));

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
  let portal = "";
  const apps = createServer((request, response) => {
    const found = new URL(request.url ?? "/", "http://apps").pathname === "/";
    response.writeHead(found ? 200 : 404, {
      "Content-Type": "text/html",
      "Content-Security-Policy": `${appPolicy}; frame-ancestors ${portal}`,
      "X-Content-Type-Options": "nosniff",
      "Referrer-Policy": "no-referrer",
      "X-DNS-Prefetch-Control": "off",
    });
    response.end(found ? sandbox : "Nothing is served here.");
  });
  await new Promise<void>((listening) => apps.listen(0, "127.0.0.1", listening));
  const appsOrigin = `http://127.0.0.1:${(apps.address() as AddressInfo).port}`;
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
        // As `Site(apps=...)` adds it: the apps' origin, the one frame the page may hold.
        "Content-Security-Policy": `${policy}; frame-src ${appsOrigin}`,
        "X-Content-Type-Options": "nosniff",
      },
    },
  });
  const [url] = server.resolvedUrls?.local ?? [];
  if (!url) {
    throw new Error("the CSP tests' page has no address");
  }
  portal = new URL(url).origin;
  project.provide("harness", url);
  project.provide("apps", appsOrigin);
  return async () => {
    apps.close();
    await server.close();
    await rm(outDir, { recursive: true, force: true });
  };
}
