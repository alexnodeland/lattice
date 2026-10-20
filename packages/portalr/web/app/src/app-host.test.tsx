/**
 * A mini app's artifact page, over a stubbed server (portalr ADR-0051): run in its sandbox on the
 * deployment's apps' origin while mini apps are on, its state written as the person viewing it,
 * and stopped when it is archived or mini apps are switched off.
 */

import { afterEach, expect, test, vi } from "vitest";
import { open } from "./test/app";
import { AT, FLAGS } from "./test/files";

const APPS = "http://127.0.0.1:9";

const app = (archived = false) => [
  {
    artifact_id: "app_1",
    version: 2,
    kind: "app",
    data: { title: "Dice", summary: "Rolls a die.", html: "<button>Roll</button>", state: {} },
    archived,
    actor: { kind: "agent", thread_id: "thr_1", run_id: "run_1" },
  },
];

/** The server: the app's revisions, and mini apps on or off as `flags` answers at each read. */
function serving(flags: () => Record<string, boolean>, archived = false) {
  return async (_request: Request, path: string) => {
    switch (path) {
      case `${AT}/artifacts/app_1/revisions`:
        return Response.json(app(archived));
      case FLAGS:
        return Response.json(flags());
      case "/grantr/v1/checks":
        return Response.json([false]);
      default:
        return undefined;
    }
  };
}

const on = () => ({ "ui:mini-apps": true });
const TITLE = "Dice: an app made by the agent";

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

test("an app runs in its sandbox, and the state it sets is the person's edit of /state", async () => {
  const sent: { type: string }[] = [];
  const { screen } = await open(
    "/t/acme/w/notes/artifacts/app_1",
    serving(on),
    (command) => {
      sent.push(command);
      return null;
    },
    { apps: APPS },
  );
  const frame = screen.getByTitle(TITLE);
  await expect.element(frame).toBeInTheDocument();
  expect(frame.element().getAttribute("src")).toBe(
    `${APPS}/?host=${encodeURIComponent(location.origin)}`,
  );
  dispatchEvent(
    new MessageEvent("message", {
      origin: APPS,
      source: (frame.element() as HTMLIFrameElement).contentWindow,
      data: JSON.stringify({
        jsonrpc: "2.0",
        id: 1,
        method: "tools/call",
        params: {
          name: "set_state",
          arguments: { patch: [{ op: "add", path: "/rolled", value: 4 }] },
        },
      }),
    }),
  );
  await vi.waitFor(() =>
    expect(sent).toContainEqual({
      type: "edit_artifact",
      artifact_id: "app_1",
      base_version: 2,
      patch: { kind: "json_patch", ops: [{ op: "replace", path: "/state", value: { rolled: 4 } }] },
    }),
  );
});

test("where the deployment names no apps' origin, an app is its label and summary", async () => {
  const { screen } = await open("/t/acme/w/notes/artifacts/app_1", serving(on));
  await expect.element(screen.getByText(/this deployment has no origin for them/)).toBeVisible();
  expect(screen.container.querySelector("iframe")).toBeNull();
});

test("an archived app runs nothing", async () => {
  const { screen } = await open("/t/acme/w/notes/artifacts/app_1", serving(on, true), undefined, {
    apps: APPS,
  });
  await expect
    .element(screen.getByText("This app is switched off: it was archived."))
    .toBeVisible();
  expect(screen.container.querySelector("iframe")).toBeNull();
});

test("mini apps switched off while an app runs stop it at the next read", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  let enabled = true;
  const { screen } = await open(
    "/t/acme/w/notes/artifacts/app_1",
    serving(() => ({ "ui:mini-apps": enabled })),
    undefined,
    { apps: APPS },
  );
  await expect.element(screen.getByTitle(TITLE)).toBeInTheDocument();
  enabled = false;
  await vi.advanceTimersByTimeAsync(30_000);
  await expect
    .element(screen.getByText("Not available in this workspace: mini apps are off."))
    .toBeVisible();
  expect(screen.container.querySelector("iframe")).toBeNull();
});
