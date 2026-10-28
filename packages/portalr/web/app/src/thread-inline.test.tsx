/**
 * Every kind the app draws, inline in the thread it was made in, over a stubbed server (portalr
 * ADR-0055): a note, with its full view; a form, sent from the thread as the reader; a native
 * file, a page at a time, its outline and its words, a workbook's cells, its download, and, where
 * its app is off or its routes aren't served, read only or its manifest alone; and a file whose
 * app's build hands it over, edited in its editor framed in the thread, each save checked in.
 */

import { afterEach, expect, test, vi } from "vitest";
import { userEvent } from "vitest/browser";
import DIAGRAM from "../../ui/csp/diagram.json";
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
  diag_1: ["excalidraw_diagram", DIAGRAM],
  form_1: ["form", POLL],
  cad_1: [
    "cad_model",
    manifest("bracket.FCStd", "application/x-extension-fcstd", "Body\n  Pad", 1),
  ],
  sub_1: ["submission", { form_id: "form_1", version: 1, values: { dish: "Soup" } }],
  dash_1: [
    "dashboard",
    {
      title: "Support this week",
      panels: [{ type: "stat", label: "Open tickets", value: 42, change: -6 }],
    },
  ],
  doc_1: ["word_document", manifest("brief.docx", DOCX, "Brief\nFees", 3)],
  book_1: ["workbook", manifest("figures.xlsx", XLSX, "Costs (A1:B3)\nPlan", null)],
  book_2: ["workbook", manifest("budget.xlsx", XLSX, "Budget", null)],
  new_1: [
    "word_document",
    { ...manifest("Travel plan.docx", DOCX, "", 1), provenance: { source: "blank" } },
  ],
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
  status?: (id: string) => Response | undefined;
  held?: { lease: unknown };
  /** An artifact's revisions, where they aren't its one version in `DATA`. */
  revisions?: (id: string) => unknown[] | undefined;
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
      const given = world.revisions?.(revisions);
      if (given !== undefined) {
        return Response.json(given);
      }
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
      if (/^\/versions\/[12]\/pages\/[12]$/.test(rest)) {
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

test("a FreeCAD model is read inline as any native file is, a page at a time", async () => {
  const { screen } = await open(THREAD, serving({ flags: { "files:freecad": true } }), undefined, {
    artifactrLog: thread([["cad_1", "cad_model"]]),
  });
  const model = screen.getByRole("listitem", { name: "bracket.FCStd" });
  await expect.element(model.getByText("3D model", { exact: true })).toBeVisible();
  await model.getByRole("radio", { name: "Outline" }).click();
  await expect.element(model.getByRole("list", { name: "Outline of bracket.FCStd" })).toBeVisible();
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
  await expect.poll(() => document.activeElement?.getAttribute("aria-label")).toBe("Full view");
});

test("a diagram opens on its canvas from its full view, and each gives the focus back", async () => {
  const { screen } = await open(THREAD, serving(), undefined, {
    artifactrLog: thread([["diag_1", "excalidraw_diagram"]]),
  });
  const card = screen.getByRole("listitem", { name: "Stack" });
  await expect.element(card.getByText("Diagram · 9 elements")).toBeVisible();
  await card.getByRole("button", { name: "Full view" }).click();
  const full = screen.getByRole("dialog", { name: "Stack" });
  await expect.element(full).toBeVisible();
  const opener = full.getByRole("button", { name: "Open canvas" });
  await opener.click();
  // The full view behind it is hidden from assistive technology while the canvas is open.
  const canvas = screen.getByRole("dialog", { name: "Stack" });
  await expect.element(canvas.getByRole("button", { name: "Close canvas" })).toBeVisible();
  await expect.poll(() => document.querySelector(".excalidraw canvas")).not.toBeNull();
  const inCanvas = () =>
    document.activeElement?.closest(".excalidraw, [data-base-ui-portal]") !== null &&
    document.activeElement !== document.body;
  // Tab stays in the canvas, the full view's own trap leaving it be.
  for (let step = 0; step < 12; step += 1) {
    await userEvent.keyboard("{Tab}");
    expect(inCanvas()).toBe(true);
  }
  // Escape closes the canvas alone: the full view stays, and the focus is the opener's again.
  await userEvent.keyboard("{Escape}");
  await expect.poll(() => document.querySelector(".excalidraw")).toBeNull();
  await expect.element(full).toBeVisible();
  await expect.poll(() => document.activeElement).toBe(opener.element());
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

test("a dashboard made in a thread shows its panels there, with its full view", async () => {
  const { screen } = await open(THREAD, serving(), undefined, {
    artifactrLog: thread([["dash_1", "dashboard"]]),
  });
  const dashboard = screen.getByRole("listitem", { name: "Support this week" });
  await expect.element(dashboard.getByText("Dashboard", { exact: true })).toBeVisible();
  await expect.element(dashboard.getByText("Open tickets")).toBeVisible();
  await expect.element(dashboard.getByText("42", { exact: true })).toBeVisible();
  await dashboard.getByRole("button", { name: "Full view" }).click();
  await expect
    .element(screen.getByRole("dialog", { name: "Support this week" }).getByText("Open tickets"))
    .toBeVisible();
});

test("an untitled artifact is named by its kind", async () => {
  const { screen } = await open(THREAD, serving(), undefined, {
    artifactrLog: thread([["sub_1", "submission"]]),
  });
  const entry = screen.getByRole("listitem", { name: "Submission" });
  await expect.element(entry.getByText("Soup")).toBeVisible();
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

/** The agent's proposal, `seq`th in the log, of what it wrote into `new_1`; resolved, if `decision`. */
const filling = (seq: number, decision?: "accept" | "reject") => [
  logged(seq, {
    type: "proposal_created",
    proposal_id: "prop_1",
    thread_id: "thr_1",
    run_id: "run_1",
    rationale: null,
    change: {
      type: "edit_artifact",
      artifact_id: "new_1",
      base_version: 1,
      summary: "Write the travel plan",
      patch: { kind: "json_patch", ops: [] },
    },
  }),
  ...(decision
    ? [
        logged(
          seq + 1,
          { type: "proposal_resolved", proposal_id: "prop_1", artifact_id: "new_1", decision },
          ALICE,
        ),
      ]
    : []),
];

test("a file the agent created blank says so, and links to its changes waiting for review", async () => {
  const { screen } = await open(THREAD, serving(), undefined, {
    artifactrLog: [...thread([["new_1", "word_document"]]), ...filling(4)],
  });
  const file = screen.getByRole("listitem", { name: "Travel plan.docx" });
  await expect.element(file.getByText("Word document", { exact: true })).toBeVisible();
  const waiting = file.getByRole("link", {
    name: "The agent's changes are waiting for your review.",
  });
  await expect.element(waiting).toHaveAttribute("href", "#proposal-prop_1");
  await expect.element(file.getByText(/^Created empty\./)).toBeVisible();
  // Nothing of an empty file is shown: no preview, views, size or check-out.
  expect(file.getByRole("radio").elements()).toHaveLength(0);
  expect(file.getByText(/version 1/).elements()).toHaveLength(0);
  expect(file.getByRole("button", { name: /Check out/ }).elements()).toHaveLength(0);
  await waiting.click();
  await expect.element(screen.getByRole("region", { name: /^Proposal: / })).toBeVisible();
  expect(document.activeElement?.id).toBe("proposal-prop_1");
});

test("a file created blank with no change waiting says only that it was created", async () => {
  const { screen } = await open(THREAD, serving(), undefined, {
    artifactrLog: [...thread([["new_1", "word_document"]]), ...filling(4, "reject")],
  });
  const file = screen.getByRole("listitem", { name: "Travel plan.docx" });
  await expect.element(file.getByText("Created empty.", { exact: true })).toBeVisible();
  expect(file.getByRole("link", { name: /waiting/ }).elements()).toHaveLength(0);
});

test("once its changes are accepted, a file created blank is read in the same place", async () => {
  const [kind, data] = DATA.new_1 ?? ["", {}];
  const written = { ...data, outline: "Day 1\nDay 2", provenance: { source: "commands" } };
  const { screen } = await open(
    THREAD,
    serving({
      revisions: (id) =>
        id === "new_1"
          ? [
              { artifact_id: id, version: 1, kind, data, archived: false, actor: AGENT },
              { artifact_id: id, version: 2, kind, data: written, archived: false, actor: ALICE },
            ]
          : undefined,
      status: (id) => (id === "new_1" ? Response.json(statusOf(id, { version: 2 })) : undefined),
    }),
    undefined,
    { artifactrLog: [...thread([["new_1", "word_document"]]), ...filling(4, "accept")] },
  );
  const file = screen.getByRole("listitem", { name: "Travel plan.docx" });
  await expect.element(file.getByText("48 kB · 1 page · version 2")).toBeVisible();
  expect(file.getByText(/Created empty/).elements()).toHaveLength(0);
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
  // No download is offered for a file whose routes can't give it.
  expect(file.getByRole("button", { name: "Download" }).elements()).toHaveLength(0);
});

test("a file's download is in its header, beside its page, once it is read, and not in its full view", async () => {
  let answer: () => void = () => {};
  const content = new Promise<void>((done) => {
    answer = done;
  });
  const saved = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  const { screen, fetched } = await open(
    THREAD,
    async (request, path) => {
      if (path.endsWith("/files/doc_1/versions/1/content")) {
        await content;
        return new Response("the file's bytes");
      }
      return serving()(request, path);
    },
    undefined,
    { artifactrLog: thread([["doc_1", "word_document"]]) },
  );
  const file = screen.getByRole("listitem", { name: "brief.docx" });
  const download = file.getByRole("button", { name: "Download", exact: true });
  await expect.element(download).toBeVisible();
  // In the header's order: the download, then its page, then its full view.
  const bar = download.element().closest("span:not(.contents)");
  const named = [...(bar?.querySelectorAll("button, a") ?? [])].map((each) =>
    each.getAttribute("aria-label"),
  );
  expect(named).toEqual(["Download", "Open its page", "Full view"]);
  await download.click();
  // Its name stays as it is downloaded; that it is busy is said beside it.
  await expect.element(download).toHaveAttribute("aria-busy", "true");
  expect(download.element().getAttribute("aria-label")).toBe("Download");
  answer();
  await expect.poll(() => saved.mock.instances.length).toBe(1);
  await expect.element(download).not.toHaveAttribute("aria-busy");
  expect(
    fetched.mock.calls.some(([input]) =>
      (input as Request).url.endsWith("/files/doc_1/versions/1/content"),
    ),
  ).toBe(true);
  await file.getByRole("button", { name: "Full view" }).click();
  const full = screen.getByRole("dialog", { name: "brief.docx" });
  await expect.element(full).toBeVisible();
  expect(full.getByRole("button", { name: "Download", exact: true }).elements()).toHaveLength(0);
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
  await book.getByRole("button", { name: "Edit in GridCraft" }).click();
  const editor = book.getByTitle("GridCraft, editing figures.xlsx");
  await expect.element(editor).toBeInTheDocument();
  const frame = editor.element() as HTMLIFrameElement;
  // The shim is told which portal origin frames it: this page's own (portalr ADR-0084).
  expect(frame.getAttribute("src")).toBe(
    `http://127.0.0.1:9/.lattice/shim.html?host=${encodeURIComponent(location.origin)}`,
  );
  expect(frame.getAttribute("sandbox")).toBe(
    "allow-scripts allow-same-origin allow-downloads allow-modals allow-forms allow-popups",
  );
  expect(frame.getAttribute("allow")).toBe("clipboard-read; clipboard-write");
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
  await expect.element(book.getByRole("button", { name: "Back to preview" })).toBeVisible();
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
  await book.getByRole("button", { name: "Edit in GridCraft" }).click();
  const editor = book.getByTitle("GridCraft, editing figures.xlsx");
  await expect.element(editor).toBeInTheDocument();
  fromShim(editor.element() as HTMLIFrameElement, { type: "lattice:failed", error: "no wasm" });
  await expect.element(book.getByText("GridCraft didn't open here")).toBeVisible();
  await expect.element(book.getByText(/^GridCraft didn't start here\./)).toBeVisible();
  await book.getByRole("button", { name: "Back to preview" }).click();
  await expect.element(editor).not.toBeInTheDocument();
  vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout"] });
  await book.getByRole("button", { name: "Edit in GridCraft" }).click();
  await expect.element(editor).toBeInTheDocument();
  vi.advanceTimersByTime(60_000);
  await expect.element(book.getByText("GridCraft didn't open here")).toBeVisible();
  vi.useRealTimers();
});

const MINE = { checked_out_by: "user:alice", expires_at: CHECKOUT.expires_at, checkout_id: "co_1" };

/**
 * A thread of bridged workbooks alice holds, each opened in its editor, ready: the frames, the
 * screen, and what the server is asked. `flags` answers the workspace's switches at each read.
 */
async function editingIn(
  books: readonly string[] = ["book_1"],
  flags: () => Record<string, boolean> = () => ({ "files:gridcraft": true }),
  lease: (id: string) => unknown = () => MINE,
  extension: () => Response = () => Response.json(CHECKOUT),
) {
  vi.stubGlobal("XMLHttpRequest", Upload);
  const opened = await open(
    THREAD,
    async (request, path) =>
      path === FLAGS
        ? Response.json(flags())
        : path === `${AT}/checkouts/co_1/extension`
          ? extension()
          : serving({
              status: (id) => Response.json({ ...statusOf(id), lease: lease(id), talk: "bridged" }),
            })(request, path),
    undefined,
    {
      artifactrLog: thread(books.map((id) => [id, "workbook"] as const)),
      editors: { "files:gridcraft": GRID },
    },
  );
  return opened;
}

/** Open a book's editor, and say it is ready: its frame. */
async function ready(screen: Awaited<ReturnType<typeof open>>["screen"], name: string) {
  const book = screen.getByRole("listitem", { name });
  await book.getByRole("button", { name: "Edit in GridCraft" }).click();
  const editor = book.getByTitle(`GridCraft, editing ${name}`);
  await expect.element(editor).toBeInTheDocument();
  const frame = editor.element() as HTMLIFrameElement;
  fromShim(frame, { type: "lattice:ready" });
  await expect
    .element(book.getByText("Open in GridCraft: saving there checks it in"))
    .toBeVisible();
  return { book, frame, editor };
}

test("a save while one is sent, or one too large, isn't sent; a malformed dirty is ignored", async () => {
  const { screen } = await editingIn();
  const { book, frame } = await ready(screen, "figures.xlsx");
  fromShim(frame, { type: "lattice:dirty", dirty: "yes" });
  fromShim(frame, { type: "lattice:dirty" });
  await expect
    .element(book.getByText("Open in GridCraft: saving there checks it in"))
    .toBeVisible();
  fromShim(frame, {
    type: "lattice:save",
    name: "figures.xlsx",
    bytes: new ArrayBuffer(26_214_401),
  });
  await expect.element(book.getByText(/^GridCraft saved figures\.xlsx at 26 MB/)).toBeVisible();
  expect(Upload.sent).toHaveLength(0);
  fromShim(frame, { type: "lattice:save", name: "figures.xlsx", bytes: new ArrayBuffer(8) });
  fromShim(frame, { type: "lattice:save", name: "figures.xlsx", bytes: new ArrayBuffer(8) });
  await expect.element(book.getByText(/^Your last save is still being checked in/)).toBeVisible();
  expect(Upload.sent).toHaveLength(1);
});

test("a refused check-in (403, 409, a lapsed check-out) keeps the editor open with the work", async () => {
  const { screen } = await editingIn();
  const { book, frame, editor } = await ready(screen, "figures.xlsx");
  fromShim(frame, { type: "lattice:dirty", dirty: true });
  for (const [status, type] of [
    [403, "forbidden"],
    [409, "invalid_state"],
    [404, "not_found"],
  ] as const) {
    fromShim(frame, { type: "lattice:save", name: "figures.xlsx", bytes: new ArrayBuffer(8) });
    await expect.poll(() => Upload.sent.length).toBeGreaterThan(0);
    (Upload.sent.at(-1) as Upload).answer(status, { detail: { type, message: "refused" } });
    await expect.element(book.getByText(/^It wasn't checked in/)).toBeVisible();
    await expect.element(editor).toBeInTheDocument();
    await expect.element(book.getByText("Unsaved changes in GridCraft")).toBeVisible();
    Upload.sent = [];
  }
});

test("closing with unsaved changes is confirmed, and leaving the page is guarded", async () => {
  const added = vi.spyOn(window, "addEventListener");
  const removed = vi.spyOn(window, "removeEventListener");
  const guards = (spy: typeof added) =>
    spy.mock.calls.filter(([type]) => type === "beforeunload").map(([, guard]) => guard);
  const { screen } = await editingIn();
  const { book, frame, editor } = await ready(screen, "figures.xlsx");
  fromShim(frame, { type: "lattice:dirty", dirty: true });
  await expect.element(book.getByText("Unsaved changes in GridCraft")).toBeVisible();
  await expect.poll(() => guards(added).length).toBe(1);
  const [guard] = guards(added);
  const leaving = new Event("beforeunload", { cancelable: true });
  (guard as (event: Event) => void)(leaving);
  expect(leaving.defaultPrevented).toBe(true);
  await book.getByRole("button", { name: "Back to preview" }).click();
  const asked = screen.getByRole("alertdialog", { name: "Back to the preview without saving?" });
  await asked.getByRole("button", { name: "Keep editing" }).click();
  await expect.element(editor).toBeInTheDocument();
  await book.getByRole("button", { name: "Back to preview" }).click();
  await screen
    .getByRole("alertdialog")
    .getByRole("button", { name: "Discard and go back" })
    .click();
  // The editor stays until the check-out is let go.
  await expect.poll(() => Upload.sent.length).toBe(1);
  (Upload.sent[0] as Upload).answer(200, { outcome: "unchanged" });
  await expect.element(editor).not.toBeInTheDocument();
  await expect.poll(() => guards(removed)).toContain(guard);
});

test("switched off while it is edited, the editor stays and says a save won't be checked in", async () => {
  let on = true;
  const { screen, queryClient } = await editingIn(["book_1"], () => ({ "files:gridcraft": on }));
  const { book, editor } = await ready(screen, "figures.xlsx");
  on = false;
  await queryClient.invalidateQueries();
  await expect
    .element(book.getByText(/^GridCraft was switched off in this workspace/))
    .toBeVisible();
  await expect.element(editor).toBeInTheDocument();
});

test("one file is edited at a time: another opens only once the first has no unsaved changes", async () => {
  const { screen } = await editingIn(["book_1", "book_2"]);
  const first = await ready(screen, "figures.xlsx");
  fromShim(first.frame, { type: "lattice:dirty", dirty: true });
  const second = screen.getByRole("listitem", { name: "budget.xlsx" });
  // Read once it comes near the window.
  second.element().scrollIntoView();
  await expect.element(first.book.getByText("Unsaved changes in GridCraft")).toBeVisible();
  await second.getByRole("button", { name: "Edit in GridCraft" }).click();
  await expect
    .element(second.getByText(/^figures\.xlsx is open in its editor with unsaved changes/))
    .toBeVisible();
  expect(second.getByTitle("GridCraft, editing budget.xlsx").elements()).toHaveLength(0);
  fromShim(first.frame, { type: "lattice:dirty", dirty: false });
  await expect
    .element(first.book.getByText("Open in GridCraft: saving there checks it in"))
    .toBeVisible();
  await second.getByRole("button", { name: "Edit in GridCraft" }).click();
  await expect.element(second.getByTitle("GridCraft, editing budget.xlsx")).toBeInTheDocument();
  await expect.element(first.editor).not.toBeInTheDocument();
});

test("an editor named at the portal's own origin isn't framed", async () => {
  const { screen } = await open(
    THREAD,
    serving({
      flags: { "files:gridcraft": true },
      status: (id) => Response.json({ ...statusOf(id), lease: MINE, talk: "bridged" }),
    }),
    undefined,
    {
      artifactrLog: thread([["book_1", "workbook"]]),
      editors: { "files:gridcraft": `${location.origin}/` },
    },
  );
  const book = screen.getByRole("listitem", { name: "figures.xlsx" });
  await expect.element(book.getByRole("button", { name: "Download again" })).toBeVisible();
  expect(book.getByRole("button", { name: "Edit in GridCraft" }).elements()).toHaveLength(0);
  expect(screen.container.querySelector("iframe")).toBeNull();
});

test("leaving for another page with unsaved changes is asked about, and staying keeps the work", async () => {
  const { screen, router } = await editingIn();
  const { book, frame, editor } = await ready(screen, "figures.xlsx");
  fromShim(frame, { type: "lattice:dirty", dirty: true });
  await expect.element(book.getByText("Unsaved changes in GridCraft")).toBeVisible();
  void router.navigate({
    to: "/t/$tenant/w/$workspace",
    params: { tenant: "acme", workspace: "notes" },
  });
  const asked = screen.getByRole("dialog", { name: "Leave GridCraft without saving?" });
  await expect.element(asked).toBeVisible();
  await asked.getByRole("button", { name: "Stay" }).click();
  await expect.element(asked).not.toBeInTheDocument();
  await expect.element(editor).toBeInTheDocument();
  expect(router.state.location.pathname).toBe(THREAD);
  void router.navigate({
    to: "/t/$tenant/w/$workspace",
    params: { tenant: "acme", workspace: "notes" },
  });
  await screen.getByRole("dialog").getByRole("button", { name: "Leave without saving" }).click();
  await expect.poll(() => router.state.location.pathname).toBe("/t/acme/w/notes");
});

test("a file isn't checked out for an editor that can't open while another has unsaved work", async () => {
  const { screen, fetched } = await editingIn(["book_1", "book_2"], undefined, (id) =>
    id === "book_1" ? MINE : null,
  );
  const first = await ready(screen, "figures.xlsx");
  fromShim(first.frame, { type: "lattice:dirty", dirty: true });
  await expect.element(first.book.getByText("Unsaved changes in GridCraft")).toBeVisible();
  const second = screen.getByRole("listitem", { name: "budget.xlsx" });
  // Read once it comes near the window.
  second.element().scrollIntoView();
  await second.getByRole("button", { name: "Edit in GridCraft" }).click();
  await expect
    .element(second.getByText(/^figures\.xlsx is open in its editor with unsaved changes/))
    .toBeVisible();
  const asked = fetched.mock.calls.filter(
    ([input]) =>
      (input as Request).method === "POST" &&
      (input as Request).url.endsWith("/files/book_2/checkouts"),
  );
  expect(asked).toHaveLength(0);
});

test("with unsaved changes, a check-out about to run out is extended, and a refusal said once", async () => {
  const soon = () => ({ ...MINE, expires_at: new Date(Date.now() + 5 * 60_000).toISOString() });
  let answer = () => Response.json(CHECKOUT);
  const { screen, fetched } = await editingIn(["book_1"], undefined, soon, () => answer());
  const extended = () =>
    fetched.mock.calls.filter(([input]) =>
      (input as Request).url.endsWith("/checkouts/co_1/extension"),
    ).length;
  const { book, frame } = await ready(screen, "figures.xlsx");
  vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
  fromShim(frame, { type: "lattice:dirty", dirty: true });
  await expect.element(book.getByText("Unsaved changes in GridCraft")).toBeVisible();
  await vi.advanceTimersByTimeAsync(60_000);
  await expect.poll(extended).toBe(1);
  answer = () =>
    Response.json(
      { detail: { type: "forbidden", message: "the check-out lapsed" } },
      { status: 403 },
    );
  await vi.advanceTimersByTimeAsync(60_000);
  await expect.element(book.getByText(/^Your check-out wasn't extended/)).toBeVisible();
  await vi.advanceTimersByTimeAsync(60_000);
  await expect.poll(extended).toBe(3);
  expect(book.getByText(/^Your check-out wasn't extended/).elements()).toHaveLength(1);
  vi.useRealTimers();
});

test("a file far from the window isn't read, near it is read and polled, and far again it rests", async () => {
  const observers: ((entries: { isIntersecting: boolean }[]) => void)[] = [];
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      constructor(seen: (entries: { isIntersecting: boolean }[]) => void) {
        observers.push(seen);
      }
      observe() {}
      disconnect() {}
    },
  );
  const { screen, fetched } = await open(THREAD, serving(), undefined, {
    artifactrLog: thread([["doc_1", "word_document"]]),
  });
  const reads = () =>
    fetched.mock.calls.filter(
      ([input]) => new URL((input as Request).url).pathname === `${AT}/files/doc_1`,
    ).length;
  await expect.element(screen.getByText("Reading the file…")).toBeVisible();
  await expect.poll(() => observers.length).toBeGreaterThan(0);
  expect(reads()).toBe(0);
  vi.useFakeTimers({ toFake: ["setInterval", "clearInterval"] });
  for (const seen of observers) seen([{ isIntersecting: true }]);
  await expect.element(screen.getByRole("img", { name: "Page 1 of 3" })).toBeVisible();
  expect(reads()).toBe(1);
  await vi.advanceTimersByTimeAsync(31_000);
  await expect.poll(reads).toBe(2);
  for (const seen of observers) seen([{ isIntersecting: false }]);
  await vi.advanceTimersByTimeAsync(0);
  await vi.advanceTimersByTimeAsync(95_000);
  expect(reads()).toBe(2);
  await expect.element(screen.getByRole("img", { name: "Page 1 of 3" })).toBeVisible();
  vi.useRealTimers();
});

test("the preview flips to the editor in the same box and back, keeping its view, and the check-out ends", async () => {
  const held = { lease: null as unknown };
  vi.stubGlobal("XMLHttpRequest", Upload);
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
  // A view chosen in the preview is kept across the flip.
  await book.getByRole("radio", { name: "Plan" }).click();
  const plan = book.getByRole("table", { name: "Plan" });
  await expect.element(plan).toBeVisible();
  const planned = plan.element();
  await book.getByRole("button", { name: "Edit in GridCraft" }).click();
  const editor = book.getByTitle("GridCraft, editing figures.xlsx");
  await expect.element(editor).toBeInTheDocument();
  // The same box: the preview hidden, not gone, and the editor where it was.
  const frame = editor.element() as HTMLIFrameElement;
  const box = frame.closest("[hidden], .flip-in")?.parentElement;
  expect(box?.className).toContain("h-[min(80dvh,48rem)]");
  expect(box?.contains(planned)).toBe(true);
  expect(planned.closest("[hidden]")).not.toBeNull();
  expect(book.getByRole("radio", { name: "Cells" }).elements()).toHaveLength(0);
  await expect
    .poll(() => document.activeElement?.getAttribute("aria-label"))
    .toBe("figures.xlsx in GridCraft");
  // Motion is reduced here: the flip turns nothing.
  expect(getComputedStyle(frame.closest(".flip-in") as Element).animationName).toBe("none");
  fromShim(frame, { type: "lattice:ready" });
  await expect
    .element(book.getByText("Open in GridCraft: saving there checks it in"))
    .toBeVisible();
  // Back, clean: the version checked out is checked in again, unchanged, which ends the check-out.
  await book.getByRole("button", { name: "Back to preview" }).click();
  // The editor stays in place while the check-out is let go, and the switch waits for it.
  await expect.poll(() => Upload.sent.length).toBe(1);
  await expect.element(editor).toBeInTheDocument();
  expect((Upload.sent[0] as Upload).url).toBe("/artifactr/v1/workspaces/notes/checkouts/co_1/file");
  held.lease = null;
  (Upload.sent[0] as Upload).answer(200, { outcome: "unchanged" });
  await expect.element(editor).not.toBeInTheDocument();
  await expect.element(plan).toBeVisible();
  expect(plan.element()).toBe(planned);
  // The focus is on the side turned to.
  await expect
    .poll(() => document.activeElement?.getAttribute("aria-label"))
    .toBe("Preview of figures.xlsx");
  await expect
    .element(book.getByText("Back to the preview: figures.xlsx is no longer checked out."))
    .toBeVisible();
  await expect.element(book.getByRole("button", { name: "Edit in GridCraft" })).toBeVisible();
});

test("back to the preview, a check-out that can't be let go says it holds; one checked in already has ended", async () => {
  const { screen } = await editingIn();
  const { book } = await ready(screen, "figures.xlsx");
  await book.getByRole("button", { name: "Back to preview" }).click();
  await expect.poll(() => Upload.sent.length).toBe(1);
  (Upload.sent[0] as Upload).answer(403, { detail: { type: "forbidden", message: "not yours" } });
  await expect
    .element(book.getByText(/^Back to the preview\. Your check-out couldn't be let go/))
    .toBeVisible();
  await ready(screen, "figures.xlsx");
  await book.getByRole("button", { name: "Back to preview" }).click();
  await expect.poll(() => Upload.sent.length).toBe(2);
  (Upload.sent[1] as Upload).answer(409, {
    detail: { type: "invalid_state", message: "checked in already" },
  });
  await expect
    .element(book.getByText("Back to the preview: figures.xlsx is no longer checked out."))
    .toBeVisible();
});

test("while a save is being checked in, going back isn't offered", async () => {
  const { screen } = await editingIn();
  const { book, frame } = await ready(screen, "figures.xlsx");
  fromShim(frame, { type: "lattice:save", name: "figures.xlsx", bytes: new ArrayBuffer(8) });
  await expect.element(book.getByText("Checking in your save")).toBeVisible();
  await expect.element(book.getByRole("button", { name: "Back to preview" })).toBeDisabled();
  fromShim(frame, { type: "lattice:dirty", dirty: true });
  await expect.element(book.getByRole("button", { name: "Back to preview" })).toBeDisabled();
});

test("a change of search or hash isn't asked about: only another page is", async () => {
  // The browser's own back and forward go through the same blocker in its history; the tests'
  // memory history moves without asking, so they are checked in the browser (see the PR).
  const { screen, router } = await editingIn();
  const { book, frame, editor } = await ready(screen, "figures.xlsx");
  fromShim(frame, { type: "lattice:dirty", dirty: true });
  await expect.element(book.getByText("Unsaved changes in GridCraft")).toBeVisible();
  router.history.push(`${THREAD}#later`);
  await expect.poll(() => router.state.location.hash).toBe("later");
  expect(screen.getByRole("dialog").elements()).toHaveLength(0);
  await expect.element(editor).toBeInTheDocument();
});

test("a file whose app has no hosted editor keeps its preview, with no switch", async () => {
  const { screen } = await open(
    THREAD,
    serving({
      flags: { "files:gridcraft": true },
      status: (id) => Response.json({ ...statusOf(id), talk: "bridged" }),
    }),
    undefined,
    { artifactrLog: thread([["book_1", "workbook"]]), editors: {} },
  );
  const book = screen.getByRole("listitem", { name: "figures.xlsx" });
  await expect.element(book.getByRole("table", { name: "Costs" })).toBeVisible();
  expect(book.getByRole("button", { name: /Edit in/ }).elements()).toHaveLength(0);
  await expect.element(book.getByRole("button", { name: "Check out and download" })).toBeVisible();
});

test("a download that fails is said below, in the file's controls, and announced by its button", async () => {
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  const { screen } = await open(
    THREAD,
    async (request, path) =>
      path.endsWith("/files/doc_1/versions/1/content")
        ? new Response(null, { status: 500 })
        : serving()(request, path),
    undefined,
    { artifactrLog: thread([["doc_1", "word_document"]]) },
  );
  const file = screen.getByRole("listitem", { name: "brief.docx" });
  await file.getByRole("button", { name: "Download", exact: true }).click();
  await expect
    .element(file.getByText("The file wasn't downloaded. Try again in a moment."))
    .toBeVisible();
  await expect
    .poll(
      () =>
        file
          .getByRole("button", { name: "Download", exact: true })
          .element()
          .parentElement?.querySelector("[role=status]")?.textContent,
    )
    .toBe("brief.docx wasn't downloaded.");
});

test("while a file's status is read, or when it can't be, no download is offered", async () => {
  const { screen } = await open(
    THREAD,
    async (request, path) =>
      path === `${AT}/files/doc_1` ? new Promise<Response>(() => {}) : serving()(request, path),
    undefined,
    { artifactrLog: thread([["doc_1", "word_document"]]) },
  );
  const reading = screen.getByRole("listitem", { name: "brief.docx" });
  await expect.element(reading.getByText("Reading the file…")).toBeVisible();
  expect(reading.getByRole("button", { name: "Download", exact: true }).elements()).toHaveLength(0);
});

test("a file whose status can't be read offers no download", async () => {
  const { screen } = await open(
    THREAD,
    serving({ status: () => Response.json({ detail: "no" }, { status: 403 }) }),
    undefined,
    { artifactrLog: thread([["doc_1", "word_document"]]) },
  );
  const file = screen.getByRole("listitem", { name: "brief.docx" });
  await expect.element(file.getByText(/^This file couldn't be read/)).toBeVisible();
  expect(file.getByRole("button", { name: "Download", exact: true }).elements()).toHaveLength(0);
});
