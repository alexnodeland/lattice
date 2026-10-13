import { randomUUID } from "node:crypto";
import { readFile, rm } from "node:fs/promises";
import { join } from "node:path";
import { Generator, getConfig } from "@tanstack/router-generator";
import { expect, test } from "vitest";
import { ROUTES } from "../vite.config";

const admin = join(import.meta.dirname, "..");

// The route tree is TanStack Router's, from src/routes/: `moon run admin:build` rewrites it. The
// check writes its own beside the committed one, since its imports are relative to where it is.
test("the committed route tree matches the routes", async () => {
  const check = `./src/routeTree.${randomUUID()}.gen.ts`;
  try {
    const config = getConfig({ ...ROUTES, generatedRouteTree: check }, admin);
    await new Generator({ config, root: admin }).run();
    const committed = await readFile(join(admin, ROUTES.generatedRouteTree), "utf8");
    expect(await readFile(join(admin, check), "utf8")).toBe(committed);
  } finally {
    await rm(join(admin, check), { force: true });
  }
});
