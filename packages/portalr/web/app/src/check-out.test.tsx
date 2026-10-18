/**
 * Checking a native file out and in, over a stubbed server and a stubbed upload (portalr
 * ADR-0049): out, with the editor opened and the head downloaded, or downloaded alone where no
 * editor is hosted; extended; in, applied, kept as a proposal, refused, too large, stopped, and
 * sent again after an answer that never came; in after its lease ran out; and what came of each,
 * said and focused.
 */

import { afterEach, expect, test, vi } from "vitest";
import { checkedIn, editorAt, refused } from "./check-out";
import { open } from "./test/app";
import { AT, FILE, FLAGS, REVISIONS, status } from "./test/files";

const EDITOR = "https://wordcraft.example.test/";
const PAGE = "/t/acme/w/notes/artifacts/doc_1";
const MINE = {
  checked_out_by: "user:alice",
  expires_at: "2026-10-17T17:30:00Z",
  checkout_id: "co_1",
};
const CHECKOUT = {
  id: "co_1",
  artifact_id: "doc_1",
  base_version: 2,
  base_sha256: "b".repeat(64),
  actor: { kind: "user", id: "alice" },
  expires_at: MINE.expires_at,
  checked_in: false,
};

/** The file, held as `held` says: checked out to alice when she asks, unless `refuse` is set. */
interface Held {
  lease: unknown;
  limit?: number;
  refuse?: number;
}

function serving(held: Held) {
  return async (request: Request, path: string) => {
    switch (path) {
      case `${AT}/artifacts/doc_1/revisions`:
        return Response.json(REVISIONS);
      case FILE:
        return Response.json({ ...status(held.lease), limit: held.limit ?? 26_214_400 });
      case `${FILE}/checkouts`:
        if (held.refuse !== undefined) {
          return Response.json(
            { detail: { type: "artifact_busy", message: "bob has the file" } },
            { status: held.refuse },
          );
        }
        held.lease = MINE;
        return Response.json(CHECKOUT, { status: 201 });
      case `${AT}/checkouts/co_1/extension`:
        return Response.json({ ...CHECKOUT, expires_at: "2026-10-17T19:00:00Z" });
      case `${FILE}/versions/2/content`:
        return request.method === "GET" ? new Response("the file's bytes") : undefined;
      case FLAGS:
        return Response.json({});
      case "/grantr/v1/checks":
        return Response.json([false]);
      default:
        return undefined;
    }
  };
}

/** An upload the test answers: each one sent is kept, in order. */
class Upload {
  static sent: Upload[] = [];
  url = "";
  status = 0;
  responseText = "";
  upload: { onprogress: ((progress: { loaded: number; total: number }) => void) | null } = {
    onprogress: null,
  };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onabort: (() => void) | null = null;
  constructor() {
    Upload.sent.push(this);
  }
  open(_method: string, url: string) {
    this.url = url;
  }
  setRequestHeader() {}
  send() {}
  abort() {
    this.onabort?.();
  }
  answer(status: number, body: unknown) {
    this.status = status;
    this.responseText = JSON.stringify(body);
    this.onload?.();
  }
}

type Screen = Awaited<ReturnType<typeof open>>["screen"];

const sent = async (count: number) => {
  await expect.poll(() => Upload.sent.length).toBe(count);
  return Upload.sent.at(-1) as Upload;
};

/** The section's word on what came of the last action, which holds the focus. */
const told = async (screen: Screen, text: string | RegExp) => {
  const alert = screen.getByRole("region", { name: "The file" }).getByText(text);
  await expect.element(alert).toBeVisible();
  await expect.poll(() => document.activeElement?.contains(alert.element())).toBe(true);
};

/** Choose a file and check it in, as alice. */
async function checkingIn(screen: Screen, body = "edited") {
  await screen.getByLabelText("The edited file").upload(new File([body], "brief.docx"));
  await expect.element(screen.getByText(/^Chosen:/)).toBeVisible();
  await screen.getByRole("button", { name: "Check in" }).click();
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  Upload.sent = [];
  sessionStorage.clear();
});

test("checking out holds the file, opens the editor apart, downloads the head, and says so", async () => {
  const opened = vi.spyOn(window, "open").mockReturnValue(null);
  const saved = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  const { screen } = await open(PAGE, serving({ lease: null }));
  await screen.getByRole("button", { name: "Check out and open WordCraft" }).click();
  await told(screen, /^Checked out until .*, and downloading\. WordCraft opened in a new tab/);
  expect(opened.mock.calls).toEqual([[EDITOR, "_blank", "noopener,noreferrer"]]);
  await expect.poll(() => saved.mock.instances.length).toBe(1);
  await expect.element(screen.getByText(/^Checked out by you until/)).toBeVisible();
  const editor = screen.getByRole("link", { name: "Open WordCraft" });
  await expect.element(editor).toHaveAttribute("href", EDITOR);
  await expect.element(editor).toHaveAttribute("rel", "noopener noreferrer");
  await expect.element(editor).toHaveAttribute("target", "_blank");
});

test("where no editor is hosted, checking out downloads alone, and says to open it oneself", async () => {
  const opened = vi.spyOn(window, "open").mockReturnValue(null);
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  const { screen } = await open(PAGE, serving({ lease: null }), undefined, { editors: {} });
  await expect.element(screen.getByText(/No editor is hosted here/)).toBeVisible();
  await screen.getByRole("button", { name: "Check out and download" }).click();
  await told(screen, /^Checked out until .*, and downloading\.$/);
  expect(opened).not.toHaveBeenCalled();
  expect(screen.getByRole("link", { name: "Open WordCraft" }).elements()).toHaveLength(0);
});

test("a check-out refused says why, opens nothing, and reads the workspace's switches again", async () => {
  const opened = vi.spyOn(window, "open").mockReturnValue(null);
  const { screen, fetched } = await open(PAGE, serving({ lease: null, refuse: 409 }));
  const flags = () =>
    fetched.mock.calls.filter(([input]) => new URL((input as Request).url).pathname === FLAGS)
      .length;
  await expect.poll(flags).toBe(1);
  await screen.getByRole("button", { name: "Check out and open WordCraft" }).click();
  await told(screen, "It wasn't checked out: bob has the file.");
  expect(opened).not.toHaveBeenCalled();
  await expect.poll(flags).toBe(2);
});

test("a check-out is extended", async () => {
  const { screen } = await open(PAGE, serving({ lease: MINE }));
  await screen.getByRole("button", { name: "Extend" }).click();
  await told(screen, "Your check-out was extended.");
});

test("a check-in sends the chosen file with its progress, and says what it made", async () => {
  vi.stubGlobal("XMLHttpRequest", Upload);
  const held: Held = { lease: MINE };
  const { screen } = await open(PAGE, serving(held));
  await checkingIn(screen);
  const upload = await sent(1);
  expect(upload.url).toBe("/artifactr/v1/workspaces/notes/checkouts/co_1/file");
  upload.upload.onprogress?.({ loaded: 3, total: 6 });
  const progress = screen.getByRole("progressbar", { name: "Checking in brief.docx" });
  await expect.element(progress).toHaveAttribute("aria-valuenow", "50");
  await expect.element(progress).toHaveAttribute("aria-valuetext", "3 bytes of 6 bytes");
  await expect.element(screen.getByRole("button", { name: "Stop" })).toHaveFocus();
  held.lease = null;
  upload.answer(200, { outcome: "applied", version: 3, proposal_id: null });
  await told(screen, "Checked in brief.docx as version 3.");
  await expect
    .element(screen.getByRole("button", { name: "Check out and open WordCraft" }))
    .toBeVisible();
});

test("a check-in stopped says it may have landed, and is sent again", async () => {
  vi.stubGlobal("XMLHttpRequest", Upload);
  const { screen } = await open(PAGE, serving({ lease: MINE }));
  await checkingIn(screen);
  await sent(1);
  await screen.getByRole("button", { name: "Stop" }).click();
  await told(screen, /what was sent may still have been checked in\. Try again\.$/);
  await expect.element(screen.getByRole("button", { name: "Try again" })).toBeVisible();
});

test("an answer that never came, where the check-in landed, is sent again and found in", async () => {
  vi.stubGlobal("XMLHttpRequest", Upload);
  const held: Held = { lease: MINE };
  const { screen } = await open(PAGE, serving(held));
  await checkingIn(screen);
  // The server took it, and let the file go; the answer never came.
  held.lease = null;
  (await sent(1)).onerror?.();
  await told(
    screen,
    "It wasn't checked in: The connection ended before the server answered. Try again.",
  );
  await expect.element(screen.getByText(/^Your check-out ran out/)).toBeVisible();
  await screen.getByRole("button", { name: "Try again" }).click();
  (await sent(2)).answer(200, { outcome: "unchanged", version: null, proposal_id: null });
  await told(screen, "brief.docx was checked in already: nothing new was made.");
});

test("sent again after a lost answer where it landed as a proposal, it is said to be one", async () => {
  vi.stubGlobal("XMLHttpRequest", Upload);
  const held: Held = { lease: MINE };
  const { screen } = await open(PAGE, serving(held));
  await checkingIn(screen);
  held.lease = null;
  (await sent(1)).onerror?.();
  await screen.getByRole("button", { name: "Try again" }).click();
  (await sent(2)).answer(409, {
    detail: { type: "invalid_state", message: "checkout co_1 was checked in" },
  });
  await told(screen, /^brief\.docx was checked in already, as a proposal: see/);
  await expect
    .element(screen.getByRole("link", { name: "the workspace's proposals" }))
    .toBeVisible();
});

test("a check-out kept in the tab is checked in after its lease ran out, as a proposal", async () => {
  vi.stubGlobal("XMLHttpRequest", Upload);
  sessionStorage.setItem("portalr:checkout:acme/notes/doc_1", "co_1");
  const { screen } = await open(PAGE, serving({ lease: null }));
  await expect.element(screen.getByText(/^Your check-out ran out/)).toBeVisible();
  expect(screen.getByRole("button", { name: "Extend" }).elements()).toHaveLength(0);
  await checkingIn(screen);
  (await sent(1)).answer(200, { outcome: "proposed", version: null, proposal_id: "p_1" });
  await told(
    screen,
    /^brief\.docx changed after you checked it out, so your check-in is a proposal/,
  );
  expect(sessionStorage.getItem("portalr:checkout:acme/notes/doc_1")).toBeNull();
});

test("a file past the limit is refused before it is sent", async () => {
  vi.stubGlobal("XMLHttpRequest", Upload);
  const { screen } = await open(PAGE, serving({ lease: MINE, limit: 4 }));
  await screen.getByLabelText("The edited file").upload(new File(["too long"], "brief.docx"));
  await told(screen, "brief.docx is 8 bytes: the largest file a check-in takes is 4 bytes.");
  await expect.element(screen.getByRole("button", { name: "Check in" })).toBeDisabled();
  expect(Upload.sent).toHaveLength(0);
});

test("an editor on the portal's own origin is never opened from it", () => {
  expect(editorAt({ "files:wordcraft": EDITOR }, "files:wordcraft")).toBe(EDITOR);
  expect(
    editorAt({ "files:wordcraft": `${location.origin}/editor/` }, "files:wordcraft"),
  ).toBeNull();
  expect(editorAt({}, "files:wordcraft")).toBeNull();
});

test("each refusal is said as the reader can act on it, with its full stop once", () => {
  const said = (status: number, reasons = ["why"]) =>
    refused("It wasn't checked in", { outcome: "refused", status, reasons }, "WordCraft");
  expect(said(409)).toBe("It wasn't checked in: why.");
  expect(said(413, ["the file is larger than 4 bytes."])).toBe(
    "It wasn't checked in: the file is larger than 4 bytes.",
  );
  expect(said(422)).toBe(
    "It wasn't checked in: WordCraft couldn't read it. Check it's the file you saved from WordCraft.",
  );
  expect(said(503)).toBe(
    "It wasn't checked in: WordCraft couldn't finish reading it. Try again in a moment.",
  );
  const answer = { outcome: "unchanged", version: null, proposal_id: null } as const;
  expect(checkedIn(answer, "brief.docx", false)).toBe(
    "Nothing in brief.docx changed, so no version was made. Your check-out has ended.",
  );
});
