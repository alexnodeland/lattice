/**
 * Runs when reflexr can't be reached: the stream never gets its welcome, and after a while the page
 * says so, where it would say it is reading for ever. The wait is shortened here.
 */

import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { page } from "vitest/browser";
import { open as opened } from "./test/admin";
import { stubSockets } from "./test/socket";

vi.mock("./runs", async (original) => ({
  ...(await original<typeof import("./runs")>()),
  PATIENCE: 80,
}));

beforeEach(async () => {
  stubSockets({ log: [], answer: () => null, mute: true });
  await page.viewport(1280, 900);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

test("a workspace that can't be reached is said to be, after a while", async () => {
  const { screen } = await opened("/t/acme/runs", ["reflexr:read_runs"], async (_request, path) =>
    path === "/artifactr/v1/workspaces"
      ? Response.json(["notes"])
      : path === "/portalr/v1/deployment/tenants"
        ? Response.json({ detail: { type: "forbidden", message: "no" } }, { status: 403 })
        : undefined,
  );
  await expect
    .element(screen.getByRole("status"))
    .toHaveTextContent("Reading the workspace's runs…");
  await expect
    .element(screen.getByRole("alert"))
    .toHaveTextContent(
      "The workspace's runs can't be reached: reflexr may be down. It keeps trying, and they appear once it answers.",
    );
});
