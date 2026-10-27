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

/** An event of the workspace's log, at `seq`, by `actor`. */
const logged = (seq: number, event: Record<string, unknown>, actor: unknown = AGENT) => ({
  type: "event",
  seq,
  id: `evt_${seq}`,
  ts: "2026-10-20T09:00:00Z",
  workspace_id: "notes",
  actor,
  event,
});

const AGENT = { kind: "agent", thread_id: "thr_1", run_id: "run_1" };

/** A thread in which alice asks for an app, and the agent makes it, then changes it. */
const THREAD = [
  logged(
    1,
    { type: "thread_created", thread_id: "thr_1", title: "Games" },
    { kind: "user", id: "alice" },
  ),
  logged(
    2,
    { type: "message_posted", thread_id: "thr_1", message_id: "msg_1", content: "Make me a game" },
    { kind: "user", id: "alice" },
  ),
  logged(3, {
    type: "artifact_created",
    artifact_id: "app_1",
    kind: "app",
    version: 1,
    data: {},
    thread_id: "thr_1",
    run_id: "run_1",
  }),
  logged(4, {
    type: "message_posted",
    thread_id: "thr_1",
    message_id: "msg_2",
    content: "Here it is.",
    run_id: "run_1",
  }),
  logged(5, {
    type: "artifact_changed",
    artifact_id: "app_1",
    kind: "app",
    version: 2,
    patch: { kind: "json_patch", ops: [] },
    summary: "",
    thread_id: "thr_1",
    run_id: "run_1",
  }),
];

test("an app made in a thread runs there, once, where it was made, at its latest version", async () => {
  const { screen } = await open(
    "/t/acme/w/notes/threads/thr_1",
    async (request, path) =>
      path === "/grantr/v1/checks"
        ? Response.json(((await request.json()) as unknown[]).map(() => true))
        : serving(on)(request, path),
    undefined,
    { apps: APPS, artifactrLog: THREAD },
  );
  const inline = screen.getByRole("listitem", { name: "Dice" });
  await expect.element(inline.getByTitle(TITLE)).toBeInTheDocument();
  await expect.element(inline.getByText(/Version 2\./)).toBeVisible();
  await expect
    .element(inline.getByRole("link", { name: "Open its page" }))
    .toHaveAttribute("href", expect.stringContaining("/artifacts/app_1"));
  expect(screen.container.querySelectorAll("iframe")).toHaveLength(1);
  const items = [...screen.container.querySelectorAll("[role=log] > ol > li")];
  expect(
    items.map((item) => item.getAttribute("aria-label") ?? item.textContent?.slice(0, 20)),
  ).toEqual([expect.anything(), "Dice", expect.anything()]);
  expect(items[0]?.textContent).toContain("Make me a game");
  expect(items[2]?.textContent).toContain("Here it is.");
});

/** The server for a thread: every check allowed, and the revisions `revisions` answers. */
function threaded(revisions: (artifact: string) => Response | undefined) {
  return async (request: Request, path: string) => {
    if (path === "/grantr/v1/checks") {
      return Response.json(((await request.json()) as unknown[]).map(() => true));
    }
    const asked = /\/artifacts\/(\w+)\/revisions$/.exec(path);
    return asked?.[1] ? revisions(asked[1]) : serving(on)(request, path);
  };
}

/** A revision of an app, as artifactr reads it. */
const revision = (id: string, version: number, title: string, state = {}) => ({
  artifact_id: id,
  version,
  kind: "app",
  data: { title, summary: "Rolls a die.", html: "<button>Roll</button>", state },
  archived: false,
  actor: AGENT,
});

test("apps made elsewhere, or in no thread, aren't shown; a second is shown where it was made", async () => {
  const log = [
    ...THREAD,
    logged(6, {
      type: "artifact_created",
      artifact_id: "app_2",
      kind: "app",
      version: 1,
      data: {},
      thread_id: "thr_1",
    }),
    logged(7, {
      type: "artifact_created",
      artifact_id: "app_3",
      kind: "app",
      version: 1,
      data: {},
    }),
  ];
  const { screen } = await open(
    "/t/acme/w/notes/threads/thr_1",
    threaded((id) => {
      const titles: Record<string, string> = { app_1: "Dice", app_2: "Coin", app_3: "Lost" };
      return Response.json([revision(id, 1, titles[id] ?? id)]);
    }),
    undefined,
    { apps: APPS, artifactrLog: log },
  );
  await expect.element(screen.getByRole("listitem", { name: "Coin" })).toBeInTheDocument();
  const items = [...screen.container.querySelectorAll("[role=log] > ol > li")];
  // A message is named by who posted it, through aria-labelledby; an app by its title.
  expect(items.map((item) => item.getAttribute("aria-label"))).toEqual([
    null,
    "Dice",
    null,
    "Coin",
  ]);
  expect(screen.container.textContent).not.toContain("Lost");
});

test("a new version keeps the frame running, and a read again that fails keeps it too", async () => {
  let read: () => Response = () => Response.json([revision("app_1", 1, "Dice")]);
  const { screen, queryClient } = await open(
    "/t/acme/w/notes/threads/thr_1",
    threaded(() => read()),
    undefined,
    { apps: APPS, artifactrLog: THREAD },
  );
  const inline = screen.getByRole("listitem", { name: "Dice" });
  await expect.element(inline.getByText(/Version 1\./)).toBeVisible();
  const frame = inline.getByTitle(TITLE).element();
  read = () =>
    Response.json([revision("app_1", 1, "Dice"), revision("app_1", 2, "Dice", { rolled: 3 })]);
  await queryClient.invalidateQueries();
  await expect.element(inline.getByText(/Version 2\./)).toBeVisible();
  expect(inline.getByTitle(TITLE).element()).toBe(frame);
  read = () => new Response(null, { status: 500 });
  await queryClient.invalidateQueries();
  await vi.waitFor(() => expect(queryClient.isFetching()).toBe(0));
  expect(inline.getByTitle(TITLE).element()).toBe(frame);
  expect(inline.element().textContent).not.toContain("couldn't be read");
});

test("an app whose first read fails says so", async () => {
  const { screen } = await open(
    "/t/acme/w/notes/threads/thr_1",
    threaded(() => new Response(null, { status: 500 })),
    undefined,
    { apps: APPS, artifactrLog: THREAD },
  );
  await expect
    .element(screen.getByText("This app couldn't be read. Reload the page to try again."))
    .toBeVisible();
});

test("the artifact's actions are a menu at its head, thumbs on it checked as given", async () => {
  const sent: { type: string }[] = [];
  const { screen } = await open(
    "/t/acme/w/notes/artifacts/app_1",
    async (request, path) =>
      path === "/grantr/v1/checks"
        ? Response.json(((await request.json()) as unknown[]).map(() => true))
        : serving(on)(request, path),
    (command) => {
      sent.push(command);
      return null;
    },
  );
  await screen.getByRole("button", { name: "Artifact actions" }).click();
  await screen.getByRole("menuitemcheckbox", { name: "Helpful" }).click();
  expect(sent.at(-1)).toMatchObject({
    type: "give_feedback",
    feedback_type: "thumbs",
    target: { kind: "artifact", artifact_id: "app_1" },
    value: { up: true },
  });
});

test("at an alias of the portal, the app runs on the apps' origin beside it (portalr ADR-0084)", async () => {
  const { screen } = await open("/t/acme/w/notes/artifacts/app_1", serving(on), () => null, {
    apps: "http://127.0.0.1:8",
    origin: "https://elsewhere.example",
    aliases: { [location.origin]: { apps: APPS, editors: {} } },
  });
  const frame = screen.getByTitle(TITLE);
  await expect
    .element(frame)
    .toHaveAttribute("src", `${APPS}/?host=${encodeURIComponent(location.origin)}`);
});

test("at an address the deployment names no apps for, the app says where to open the portal", async () => {
  const { screen } = await open("/t/acme/w/notes/artifacts/app_1", serving(on), () => null, {
    apps: APPS,
    origin: "https://elsewhere.example",
    aliases: {
      "https://m.my-tailnet.ts.net": { apps: "https://m.my-tailnet.ts.net:8801", editors: {} },
    },
  });
  await expect
    .element(screen.getByText(/Apps don't run at this address/))
    .toHaveTextContent(
      "Apps don't run at this address: open the portal at https://elsewhere.example or https://m.my-tailnet.ts.net.",
    );
  expect(screen.container.querySelector("iframe")).toBeNull();
});
