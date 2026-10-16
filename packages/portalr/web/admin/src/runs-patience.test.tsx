/**
 * Runs when reflexr can't be reached: the stream never gets its welcome, and after a while the page
 * says so, where it would say it is reading for ever. The wait is shortened here.
 */

import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { page } from "vitest/browser";
import { open as opened } from "./test/admin";
import { frame, stubSockets } from "./test/socket";

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

test("a replay that takes long is reading, and not a workspace that can't be reached", async () => {
  stubSockets({
    log: [frame(1, { type: "reflexr:run_started", run_id: "r1", rule: "x", attempt: 1 })],
    answer: () => null,
    holdReplay: true,
  });
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
  // Long past the wait for a welcome: the welcome came, so it is not a stream that can't connect.
  await new Promise((resolve) => setTimeout(resolve, 400));
  await expect
    .element(screen.getByRole("status"))
    .toHaveTextContent("Reading the workspace's runs…");
  await expect.element(screen.getByRole("alert")).not.toBeInTheDocument();
});
