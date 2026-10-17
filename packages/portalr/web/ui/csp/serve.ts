/**
 * Build the CSP tests' page as app and admin are built, and serve it with portalr's
 * Content-Security-Policy, which `policy.txt` holds and a portalr test holds to the router's own.
 */

import { readFile, rm } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { build, type InlineConfig, preview } from "vite";
import type { TestProject } from "vitest/node";

declare module "vitest" {
  export interface ProvidedContext {
    /** Where the page is served. */
    harness: string;
  }
}

const root = fileURLToPath(new URL(".", import.meta.url));
const outDir = fileURLToPath(new URL("../node_modules/.csp", import.meta.url));

export default async function serve(project: TestProject) {
  const policy = (await readFile(new URL("policy.txt", import.meta.url), "utf8")).trim();
  const config: InlineConfig = {
    configFile: false,
    root,
    // Its one chunk is larger than Vite's warning: it is never shipped, so only errors are said.
    logLevel: "error",
    plugins: [react(), tailwindcss()],
    publicDir: "../public",
    build: { outDir, emptyOutDir: true },
  };
  await build(config);
  const server = await preview({
    ...config,
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
