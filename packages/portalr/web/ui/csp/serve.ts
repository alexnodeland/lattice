/**
 * Build the CSP tests' page, and serve it with the Content-Security-Policy both UIs share, which
 * `policy.txt` holds and a portalr test holds to the router's own.
 */

import { execFile } from "node:child_process";
import { readFile, rm } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";
import { preview } from "vite";
import type { TestProject } from "vitest/node";

declare module "vitest" {
  export interface ProvidedContext {
    /** Where the page is served. */
    harness: string;
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
    { cwd: ui },
  );
  const policy = (await readFile(new URL("policy.txt", import.meta.url), "utf8")).trim();
  const server = await preview({
    configFile: false,
    root: fileURLToPath(new URL(".", import.meta.url)),
    logLevel: "error",
    build: { outDir },
    preview: {
      host: "127.0.0.1",
      port: 0,
      headers: { "Content-Security-Policy": policy, "X-Content-Type-Options": "nosniff" },
    },
  });
  const [url] = server.resolvedUrls?.local ?? [];
  if (!url) {
    throw new Error("the CSP tests' page has no address");
  }
  project.provide("harness", url);
  return async () => {
    await server.close();
    await rm(outDir, { recursive: true, force: true });
  };
}
