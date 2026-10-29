/**
 * A native file edited here on a phone (portalr ADR-0090): its editor takes the whole window, with
 * a bar that names the file and goes back, its check-out's state and what is said of it in sight,
 * and its own tab offered. The editor is a stub: no build answers at its address.
 */

import { afterEach, expect, test, vi } from "vitest";
import { page, userEvent } from "vitest/browser";
import { axeViolations } from "../../ui/src/test/axe";
import { open } from "./test/app";
import { AT, FLAGS, Upload } from "./test/files";

const ALICE = { kind: "user", id: "alice" };
const XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
// Refused at once, as no editor answers there.
const GRID = "http://127.0.0.1:9/";

const LOG = [
  { type: "thread_created", thread_id: "thr_1", title: "Work" },
  { type: "message_posted", thread_id: "thr_1", message_id: "msg_1", content: "Make it" },
  {
    type: "artifact_created",
    artifact_id: "book_1",
    kind: "workbook",
    version: 1,
    data: {},
    thread_id: "thr_1",
    run_id: "run_1",
  },
].map((event, index) => ({
  type: "event",
  seq: index + 1,
  id: `evt_${index + 1}`,
  ts: "2026-10-28T09:00:00Z",
  workspace_id: "notes",
  actor: ALICE,
  event,
}));

const MANIFEST = {
  name: "figures.xlsx",
  content: { sha256: "a".repeat(64), size: 48_213, media_type: XLSX },
  fingerprint: "f".repeat(64),
  text: null,
  review: null,
  outline: "Costs",
  pages: null,
  provenance: { source: "check_in" },
};

const LEASE = { checked_out_by: "user:alice", expires_at: "2026-10-28T17:30:00Z" };

async function serve(request: Request, path: string) {
  if (path === "/grantr/v1/checks") {
    return Response.json(((await request.json()) as unknown[]).map(() => true));
  }
  if (path === FLAGS) {
    return Response.json({ "files:gridcraft": true });
  }
  if (path.endsWith("/artifacts/book_1/revisions")) {
    return Response.json([
      { artifact_id: "book_1", version: 1, kind: "workbook", data: MANIFEST, archived: false },
    ]);
  }
  if (path === `${AT}/files/book_1`) {
    return Response.json({
      artifact_id: "book_1",
      version: 1,
      name: "figures.xlsx",
      media_type: XLSX,
      size: 48_213,
      outline: "Costs",
      pages: null,
      lease: held.lease,
      talk: "bridged",
      enabled: true,
      limit: 26_214_400,
    });
  }
  if (path === `${AT}/files/book_1/checkouts` && request.method === "POST") {
    held.lease = { ...LEASE, checkout_id: "co_1" };
    return Response.json(
      {
        id: "co_1",
        artifact_id: "book_1",
        base_version: 1,
        base_sha256: "b".repeat(64),
        actor: ALICE,
        expires_at: LEASE.expires_at,
        checked_in: false,
      },
      { status: 201 },
    );
  }
  if (path === `${AT}/checkouts/co_1/release` || path === `${AT}/checkouts/co_1`) {
    held.lease = null;
    return new Response(null, { status: 204 });
  }
  if (path === `${AT}/files/book_1/versions/1/content`) {
    return new Response("the file's bytes");
  }
  return undefined;
}

const held: { lease: unknown } = { lease: null };

afterEach(() => {
  held.lease = null;
  Upload.sent = [];
  vi.unstubAllGlobals();
});

function fromShim(frame: HTMLIFrameElement, data: unknown) {
  dispatchEvent(
    new MessageEvent("message", {
      origin: new URL(GRID).origin,
      source: frame.contentWindow,
      data,
    }),
  );
}

test("on a phone, a file's editor takes the whole window, with its name, its state and a way back", async () => {
  const { screen } = await open("/t/acme/w/notes/threads/thr_1", serve, undefined, {
    artifactrLog: LOG,
    editors: { "files:gridcraft": GRID },
  });
  const book = screen.getByRole("listitem", { name: "figures.xlsx" });
  await book.getByRole("button", { name: "Edit in GridCraft" }).click();
  const window_ = screen.getByRole("dialog", { name: "figures.xlsx" });
  await expect.element(window_).toBeVisible();
  const back = window_.getByRole("button", { name: "Back" });
  await expect.poll(() => document.activeElement).toBe(back.element());
  // The frame is the window's width in CSS pixels, and most of its height: not shrunk in a column.
  const frame = window_
    .getByTitle("GridCraft, editing figures.xlsx")
    .element() as HTMLIFrameElement;
  expect(frame.getAttribute("sandbox")).toBe(
    "allow-scripts allow-same-origin allow-downloads allow-modals allow-forms allow-popups",
  );
  expect(frame.getBoundingClientRect().width).toBe(innerWidth);
  expect(frame.getBoundingClientRect().height).toBeGreaterThan(innerHeight * 0.7);
  // Its own tab, at the editor's address for this origin, which can't reach the page.
  const own = window_.getByRole("link", { name: /^Open in its own tab/ });
  expect(own.element().getAttribute("href")).toBe(GRID);
  expect(own.element().getAttribute("rel")).toBe("noopener noreferrer");
  fromShim(frame, { type: "lattice:ready", version: "0.8.0" });
  await expect
    .element(window_.getByText("Open in GridCraft: saving there checks it in"))
    .toBeVisible();
  expect(await axeViolations(window_.element())).toEqual([]);
  // What is said of it is said here, where the page's is out of sight.
  fromShim(frame, { type: "lattice:save", name: "figures.pdf", bytes: new ArrayBuffer(4) });
  await expect
    .element(window_.getByText(/^GridCraft saved figures\.pdf, which isn't checked in/))
    .toBeVisible();
  // With unsaved changes, Escape keeps it, and Back asks first.
  fromShim(frame, { type: "lattice:dirty", dirty: true });
  await expect.element(window_.getByText("Unsaved changes in GridCraft")).toBeVisible();
  await userEvent.keyboard("{Escape}");
  await expect.element(window_).toBeVisible();
  await window_.getByRole("button", { name: "Back" }).click();
  const ask = screen.getByRole("alertdialog", { name: "Back to the preview without saving?" });
  await ask.getByRole("button", { name: "Keep editing" }).click();
  await expect.element(window_).toBeVisible();
  fromShim(frame, { type: "lattice:dirty", dirty: false });
  await window_.getByRole("button", { name: "Back" }).click();
  await expect.element(window_).not.toBeInTheDocument();
  // Back on the preview it turned from.
  await expect
    .poll(() => document.activeElement?.getAttribute("aria-label"))
    .toBe("Preview of figures.xlsx");
});

test("turned wider, it keeps its frame; a save checked in closes it and is said on the page", async () => {
  vi.stubGlobal("XMLHttpRequest", Upload);
  const { screen } = await open("/t/acme/w/notes/threads/thr_1", serve, undefined, {
    artifactrLog: LOG,
    editors: { "files:gridcraft": GRID },
  });
  const book = screen.getByRole("listitem", { name: "figures.xlsx" });
  await book.getByRole("button", { name: "Edit in GridCraft" }).click();
  const window_ = screen.getByRole("dialog", { name: "figures.xlsx" });
  await expect.element(window_).toBeVisible();
  const frame = window_.getByTitle("GridCraft, editing figures.xlsx").element();
  // Past 48rem, as a phone on its side: the same frame, not loaded again, in the same window.
  const [width, height] = [innerWidth, innerHeight];
  await page.viewport(900, 430);
  await expect.poll(() => innerWidth).toBe(900);
  expect(window_.getByTitle("GridCraft, editing figures.xlsx").element()).toBe(frame);
  await page.viewport(width, height);
  const shim = frame as HTMLIFrameElement;
  fromShim(shim, { type: "lattice:ready", version: "0.8.0" });
  await expect
    .element(window_.getByText("Open in GridCraft: saving there checks it in"))
    .toBeVisible();
  fromShim(shim, { type: "lattice:save", name: "figures.xlsx", bytes: new ArrayBuffer(8) });
  await expect.poll(() => Upload.sent.length).toBe(1);
  held.lease = null;
  (Upload.sent[0] as Upload).answer(200, { outcome: "applied", version: 2 });
  await expect.element(window_).not.toBeInTheDocument();
  await expect.element(book.getByText("Checked in figures.xlsx as version 2.")).toBeVisible();
});
