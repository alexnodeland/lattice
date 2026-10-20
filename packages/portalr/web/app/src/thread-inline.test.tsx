/**
 * Every kind the app draws, inline in the thread it was made in, over a stubbed server (portalr
 * ADR-0055): a note, with its full view; a form, sent from the thread as the reader; a native
 * file, a page at a time, its outline and its words, a workbook's cells, its download, and, where
 * its app is off or its routes aren't served, read only or its manifest alone; and a file whose
 * app's build hands it over, edited in its editor framed in the thread, each save checked in.
 */

import { afterEach, expect, test, vi } from "vitest";
import { open } from "./test/app";
import { AT, FLAGS, PNG, Upload } from "./test/files";
import { kindName } from "./thread-artifact";

const THREAD = "/t/acme/w/notes/threads/thr_1";
const AGENT = { kind: "agent", thread_id: "thr_1", run_id: "run_1" };
const ALICE = { kind: "user", id: "alice" };
const DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
const XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
// Refused at once, as no editor answers there: a host name that resolves nowhere stalls the
// frame's reads, and the page's with them, for seconds.
const GRID = "http://127.0.0.1:9/";

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

/** A thread in which alice asks, and the agent makes an artifact of each id and kind given. */
const thread = (made: readonly (readonly [string, string])[]) => [
  logged(1, { type: "thread_created", thread_id: "thr_1", title: "Work" }, ALICE),
  logged(
    2,
    { type: "message_posted", thread_id: "thr_1", message_id: "msg_1", content: "Make them" },
    ALICE,
  ),
  ...made.map(([id, kind], index) =>
    logged(3 + index, {
      type: "artifact_created",
      artifact_id: id,
      kind,
      version: 1,
      data: {},
      thread_id: "thr_1",
      run_id: "run_1",
    }),
  ),
];

const POLL = {
  title: "Lunch",
  schema: {
    type: "object",
    properties: { dish: { type: "string", title: "Dish", enum: ["Soup", "Salad"] } },
    required: ["dish"],
  },
  ui: { submit_label: "Vote" },
  submissions: "once",
  closed: false,
};

/** A native file's manifest, as artifactr keeps it. */
const manifest = (name: string, mediaType: string, outline: string, pages: number | null) => ({
  name,
  content: { sha256: "a".repeat(64), size: 48_213, media_type: mediaType },
  fingerprint: "f".repeat(64),
  text: null,
  review: null,
  outline,
  pages,
  provenance: { source: "check_in" },
});

const DATA: Record<string, readonly [string, Record<string, unknown>]> = {
  note_1: ["note", { text: "# Plan\n\nShip the **brief** on Friday." }],
  form_1: ["form", POLL],
  doc_1: ["word_document", manifest("brief.docx", DOCX, "Brief\nFees", 3)],
  book_1: ["workbook", manifest("figures.xlsx", XLSX, "Costs (A1:B3)\nPlan", null)],
};

/** A file's status, as native files' routes answer it. */
const statusOf = (id: string, overrides: Record<string, unknown> = {}) => {
  const [, data] = DATA[id] ?? ["", {}];
  const facts = data as ReturnType<typeof manifest>;
  return {
    artifact_id: id,
    version: 1,
    name: facts.name,
    media_type: facts.content.media_type,
    size: facts.content.size,
    outline: facts.outline,
    pages: facts.pages,
    lease: null,
    talk: "save",
    enabled: true,
    limit: 26_214_400,
    ...overrides,
  };
};

const CHECKOUT = {
  id: "co_1",
  artifact_id: "book_1",
  base_version: 1,
  base_sha256: "b".repeat(64),
  actor: ALICE,
  expires_at: "2026-10-20T17:30:00Z",
  checked_in: false,
};

interface World {
  flags?: Record<string, boolean>;
  status?: (id: string) => Response;
  held?: { lease: unknown };
}

/** The server: every check allowed, each artifact's revisions, files' routes as `world` says. */
function serving(world: World = {}) {
  return async (request: Request, path: string) => {
    if (path === "/grantr/v1/checks") {
      return Response.json(((await request.json()) as unknown[]).map(() => true));
    }
    if (path === FLAGS) {
      return Response.json(world.flags ?? { "ui:forms": true });
    }
    const revisions = /\/artifacts\/(\w+)\/revisions$/.exec(path)?.[1];
    if (revisions !== undefined) {
      const [kind, data] = DATA[revisions] ?? ["note", {}];
      return Response.json([
        { artifact_id: revisions, version: 1, kind, data, archived: false, actor: AGENT },
      ]);
    }
    const file = new RegExp(`^${AT}/files/(\\w+)(/.*)?$`).exec(path);
    if (file?.[1] !== undefined) {
      const [, id, rest = ""] = file;
      if (rest === "") {
        return (
          world.status?.(id) ??
          Response.json({ ...statusOf(id), ...(world.held && { lease: world.held.lease }) })
        );
      }
      if (rest === "/checkouts" && request.method === "POST") {
        if (world.held) {
          world.held.lease = {
            checked_out_by: "user:alice",
            expires_at: CHECKOUT.expires_at,
            checkout_id: "co_1",
          };
        }
        return Response.json(CHECKOUT, { status: 201 });
      }
      if (/^\/versions\/1\/pages\/[12]$/.test(rest)) {
        return new Response(PNG);
      }
      if (rest === "/versions/1/text") {
        return new Response(
          id === "book_1" ? "Costs\nItem\tCost\nPaper\t12\n\nPlan\nWeek\tGoal" : "Brief\nFees",
        );
      }
      if (rest === "/versions/1/content") {
        return new Response("the file's bytes");
      }
    }
    return undefined;
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  Upload.sent = [];
  sessionStorage.clear();
});

test("a kind is named as people say it: a native file by its type", () => {
  expect(kindName("note", {})).toBe("Note");
  expect(kindName("tracker_item", {})).toBe("Tracker item");
  expect(kindName("word_document", DATA.doc_1?.[1] ?? {})).toBe("Word document");
});

test("a note is shown where it was made, named, with a full view that keeps it", async () => {
  const { screen } = await open(THREAD, serving(), undefined, {
    artifactrLog: thread([["note_1", "note"]]),
  });
  const note = screen.getByRole("listitem", { name: "Plan" });
  await expect.element(note.getByRole("heading", { name: "Plan" })).toBeVisible();
  await expect.element(note.getByText("Note", { exact: true })).toBeVisible();
  await note.getByRole("button", { name: "Full view" }).click();
  const full = screen.getByRole("dialog", { name: "Plan" });
  await expect.element(full).toBeVisible();
  const back = full.getByRole("button", { name: "Back to the page" });
  await expect.poll(() => document.activeElement).toBe(back.element());
  // The page behind it is inert, and Escape brings it back.
  expect(screen.container.querySelector("[role=log]")?.closest("[inert]")).toBeNull();
  expect(document.querySelector("[inert]")).not.toBeNull();
  document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  await expect.element(full).not.toBeInTheDocument();
  expect(document.querySelector("[inert]")).toBeNull();
  await expect.poll(() => document.activeElement?.textContent).toContain("Full view");
});

test("a form made in a thread is sent from it, as the reader", async () => {
  const sent: { type: string; kind?: string }[] = [];
  const { screen } = await open(
    THREAD,
    serving(),
    (command) => {
      sent.push(command);
      return null;
    },
    { artifactrLog: thread([["form_1", "form"]]) },
  );
  const form = screen.getByRole("listitem", { name: "Lunch" });
  await form.getByRole("radio", { name: "Soup" }).click();
  await form.getByRole("button", { name: "Vote" }).click();
  await expect
    .poll(() => sent.find((command) => command.type === "create_artifact"))
    .toMatchObject({ kind: "submission" });
});

test("a native file is read a page at a time, with its outline and words, and downloaded", async () => {
  const saved = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  const { screen } = await open(THREAD, serving(), undefined, {
    artifactrLog: thread([["doc_1", "word_document"]]),
  });
  const file = screen.getByRole("listitem", { name: "brief.docx" });
  await expect.element(file.getByText("Word document", { exact: true })).toBeVisible();
  await expect.element(file.getByText("48 kB · 3 pages · version 1")).toBeVisible();
  await expect.element(file.getByRole("img", { name: "Page 1 of 3" })).toBeVisible();
  await expect.element(file.getByRole("button", { name: "Previous page" })).toBeDisabled();
  await file.getByRole("button", { name: "Next page" }).click();
  await expect.element(file.getByRole("img", { name: "Page 2 of 3" })).toBeVisible();
  // Page 3 isn't served: it says it couldn't be shown, and the file can still be downloaded.
  await file.getByRole("button", { name: "Next page" }).click();
  await expect.element(file.getByText(/This page couldn't be shown/)).toBeVisible();
  await expect.element(file.getByRole("button", { name: "Next page" })).toBeDisabled();
  await file.getByRole("radio", { name: "Outline" }).click();
  await expect
    .element(file.getByRole("list", { name: "Outline of brief.docx" }))
    .toHaveTextContent("BriefFees");
  await file.getByRole("radio", { name: "Text" }).click();
  await expect
    .element(file.getByRole("region", { name: "Text of brief.docx" }))
    .toHaveTextContent("Brief Fees");
  await file.getByRole("button", { name: "Download" }).click();
  await expect.poll(() => saved.mock.instances.length).toBe(1);
  await expect
    .element(file.getByRole("button", { name: "Check out and open WordCraft" }))
    .toBeVisible();
});

test("a workbook, whose app renders no page, shows its sheets' cells", async () => {
  const { screen } = await open(THREAD, serving(), undefined, {
    artifactrLog: thread([["book_1", "workbook"]]),
  });
  const book = screen.getByRole("listitem", { name: "figures.xlsx" });
  const costs = book.getByRole("table", { name: "Costs" });
  await expect.element(costs).toBeVisible();
  await expect.element(costs.getByRole("cell", { name: "Paper" })).toBeVisible();
  await expect.element(costs.getByRole("columnheader", { name: "B" })).toBeVisible();
  expect(book.getByRole("radio", { name: "Pages" }).elements()).toHaveLength(0);
  await book.getByRole("radio", { name: "Plan" }).click();
  await expect
    .element(book.getByRole("table", { name: "Plan" }).getByRole("cell", { name: "Goal" }))
    .toBeVisible();
});

test("where its app is off, a file is only read", async () => {
  const off = await open(THREAD, serving({ flags: { "files:wordcraft": false } }), undefined, {
    artifactrLog: thread([["doc_1", "word_document"]]),
  });
  await expect.element(off.screen.getByText(/^WordCraft is off in this workspace/)).toBeVisible();
  expect(off.screen.getByRole("button", { name: /Check out/ }).elements()).toHaveLength(0);
});

test("where native files' routes aren't served, a file is its manifest", async () => {
  const unserved = await open(
    THREAD,
    serving({ status: () => Response.json({ detail: "not here" }, { status: 404 }) }),
    undefined,
    { artifactrLog: thread([["doc_1", "word_document"]]) },
  );
  const file = unserved.screen.getByRole("listitem", { name: "brief.docx" });
  await expect.element(file.getByText("Word document · 48 kB · 3 pages")).toBeVisible();
  await expect.element(file.getByRole("region", { name: "Outline" })).toBeVisible();
});

test("a file's status that can't be read says so", async () => {
  const { screen } = await open(
    THREAD,
    serving({ status: () => Response.json({ detail: "no" }, { status: 403 }) }),
    undefined,
    { artifactrLog: thread([["doc_1", "word_document"]]) },
  );
  await expect
    .element(screen.getByText(/^This file couldn't be read: its pages, and who has it\./))
    .toBeVisible();
});

/** The editor's frame, and a message from it, as its shim would send one. */
function fromShim(frame: HTMLIFrameElement, data: unknown, origin = new URL(GRID).origin) {
  dispatchEvent(new MessageEvent("message", { origin, source: frame.contentWindow, data }));
}

test("a workbook whose build hands it over is edited in its editor, framed here, and each save checked in", async () => {
  vi.stubGlobal("XMLHttpRequest", Upload);
  const held = { lease: null as unknown };
  const { screen, fetched } = await open(
    THREAD,
    serving({
      held,
      flags: { "files:gridcraft": true },
      status: (id) => Response.json({ ...statusOf(id), lease: held.lease, talk: "bridged" }),
    }),
    undefined,
    { artifactrLog: thread([["book_1", "workbook"]]), editors: { "files:gridcraft": GRID } },
  );
  const book = screen.getByRole("listitem", { name: "figures.xlsx" });
  await book.getByRole("button", { name: "Edit here in GridCraft" }).click();
  const editor = book.getByTitle("GridCraft, editing figures.xlsx");
  await expect.element(editor).toBeInTheDocument();
  const frame = editor.element() as HTMLIFrameElement;
  expect(frame.getAttribute("src")).toBe("http://127.0.0.1:9/.lattice/shim.html");
  expect(frame.getAttribute("sandbox")).toBe(
    "allow-scripts allow-same-origin allow-downloads allow-modals",
  );
  await expect.element(book.getByText("Opening figures.xlsx in GridCraft")).toBeVisible();
  // A message from another origin, or another window, is not heard.
  fromShim(frame, { type: "lattice:ready" }, "https://elsewhere.example.test");
  dispatchEvent(
    new MessageEvent("message", { origin: new URL(GRID).origin, data: { type: "lattice:ready" } }),
  );
  fromShim(frame, "lattice:ready");
  expect(
    fetched.mock.calls.some(([input]) =>
      (input as Request).url.endsWith("/files/book_1/versions/1/content"),
    ),
  ).toBe(false);
  fromShim(frame, { type: "lattice:ready", version: "0.8.0" });
  await expect
    .element(book.getByText("Open in GridCraft: saving there checks it in"))
    .toBeVisible();
  expect(
    fetched.mock.calls.some(([input]) =>
      (input as Request).url.endsWith("/files/book_1/versions/1/content"),
    ),
  ).toBe(true);
  fromShim(frame, { type: "lattice:dirty", dirty: true });
  await expect.element(book.getByText("Unsaved changes in GridCraft")).toBeVisible();
  await expect.element(book.getByRole("button", { name: "Close without saving" })).toBeVisible();
  // An export in another format isn't checked in.
  fromShim(frame, { type: "lattice:save", name: "figures.pdf", bytes: new ArrayBuffer(4) });
  await expect
    .element(book.getByText(/^GridCraft saved figures\.pdf, which isn't checked in/))
    .toBeVisible();
  expect(Upload.sent).toHaveLength(0);
  fromShim(frame, { type: "lattice:save", name: "figures.xlsx", bytes: new ArrayBuffer(8) });
  await expect.element(book.getByText("Checking in your save")).toBeVisible();
  await expect.poll(() => Upload.sent.length).toBe(1);
  const upload = Upload.sent[0] as Upload;
  expect(upload.url).toBe("/artifactr/v1/workspaces/notes/checkouts/co_1/file");
  expect((upload.body as File).name).toBe("figures.xlsx");
  expect((upload.body as File).size).toBe(8);
  held.lease = null;
  upload.answer(200, { outcome: "applied", version: 2 });
  await expect.element(book.getByText("Checked in figures.xlsx as version 2.")).toBeVisible();
  await expect.element(editor).not.toBeInTheDocument();
});

test("an editor that fails, or never starts, says so, and can be closed and opened again", async () => {
  const held = {
    lease: { checked_out_by: "user:alice", expires_at: CHECKOUT.expires_at, checkout_id: "co_1" },
  };
  const { screen } = await open(
    THREAD,
    serving({
      held,
      flags: { "files:gridcraft": true },
      status: (id) => Response.json({ ...statusOf(id), lease: held.lease, talk: "bridged" }),
    }),
    undefined,
    { artifactrLog: thread([["book_1", "workbook"]]), editors: { "files:gridcraft": GRID } },
  );
  const book = screen.getByRole("listitem", { name: "figures.xlsx" });
  await book.getByRole("button", { name: "Edit here in GridCraft" }).click();
  const editor = book.getByTitle("GridCraft, editing figures.xlsx");
  await expect.element(editor).toBeInTheDocument();
  fromShim(editor.element() as HTMLIFrameElement, { type: "lattice:failed", error: "no wasm" });
  await expect.element(book.getByText("GridCraft didn't open here")).toBeVisible();
  await expect.element(book.getByText(/^GridCraft didn't start here\./)).toBeVisible();
  await book.getByRole("button", { name: "Close GridCraft" }).click();
  await expect.element(editor).not.toBeInTheDocument();
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  await book.getByRole("button", { name: "Edit here in GridCraft" }).click();
  await expect.element(editor).toBeInTheDocument();
  vi.advanceTimersByTime(60_000);
  await expect.element(book.getByText("GridCraft didn't open here")).toBeVisible();
  vi.useRealTimers();
});
