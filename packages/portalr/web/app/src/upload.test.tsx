/**
 * Uploading files on the artifacts page and in a thread, over a stubbed server and stubbed
 * uploads (native files ADR-0017): several files sent one after another with their progress, each
 * of the kind its extension says and with an id of its own, kept when sent again; a file of no
 * kind, of several, of an app that is off, or too large never sent; stopped; each refusal said in
 * words of the portal's; and nothing shown to whoever may not upload.
 */

import { afterEach, expect, test, vi } from "vitest";
import { open } from "./test/app";
import { AT, Upload } from "./test/files";
import { appOf, kindsOf, uploadRefused } from "./upload";

const PAGE = "/t/acme/w/notes/artifacts";
const KINDS = [
  { kind: "word_document", extensions: [".docx"], enabled: true },
  { kind: "workbook", extensions: [".xlsx"], enabled: false },
  { kind: "drawing", extensions: [".dwg", ".dxf"], enabled: true },
  { kind: "other_drawing", extensions: [".DXF"], enabled: true },
];

function serving(uploads: unknown) {
  return async (_request: Request, path: string) =>
    path === `${AT}/uploads` ? Response.json(uploads) : undefined;
}

const offered = (change: object = {}) => ({ allowed: true, limit: 1000, kinds: KINDS, ...change });

const sent = async (count: number) => {
  await expect.poll(() => Upload.sent.length).toBe(count);
  return Upload.sent.at(-1) as Upload;
};

const query = (upload: Upload) => new URL(upload.url, location.href).searchParams;

afterEach(() => {
  vi.unstubAllGlobals();
  Upload.sent = [];
});

test("files chosen together are sent one after another, each of its kind, and said done", async () => {
  vi.stubGlobal("XMLHttpRequest", Upload);
  const { screen } = await open(PAGE, serving(offered()));
  const input = screen.getByLabelText("Upload files");
  await expect.element(input).toHaveAttribute("accept", ".docx,.dwg,.dxf,.DXF");
  await expect
    .element(input)
    .toHaveAccessibleDescription(".docx, .dwg, .dxf, .DXF, up to 1 kB each. Or drop them here.");
  await input.upload([new File(["one"], "brief.docx"), new File(["two"], "plan.dwg")]);
  const first = await sent(1);
  expect(first.url).toMatch(/^\/artifactr\/v1\/workspaces\/notes\/files\?/);
  expect(Object.fromEntries(query(first))).toMatchObject({
    kind: "word_document",
    name: "brief.docx",
  });
  expect(query(first).get("artifact_id")).toMatch(/^art_[0-9a-f]{16}$/);
  expect(first.body).toBeInstanceOf(File);
  first.upload.onprogress?.({ loaded: 1, total: 3 });
  const progress = screen.getByRole("progressbar", { name: "Uploading brief.docx" });
  await expect.element(progress).toHaveAttribute("aria-valuenow", "33");
  await expect.element(screen.getByText("3 bytes, waiting")).toBeVisible();
  expect(Upload.sent).toHaveLength(1);
  first.answer(201, { outcome: "applied", artifact_id: "art_1", version: 1, proposal_id: null });
  const second = await sent(2);
  expect(query(second).get("kind")).toBe("drawing");
  second.answer(201, {
    outcome: "proposed",
    artifact_id: "art_2",
    version: null,
    proposal_id: "p_1",
  });
  await expect.element(screen.getByText("Uploaded brief.docx.")).toBeVisible();
  await expect
    .element(screen.getByRole("link", { name: "the workspace's proposals" }))
    .toBeVisible();
  await expect
    .element(screen.getByRole("status").filter({ hasText: /^plan\.dwg is a proposal/ }))
    .toBeInTheDocument();
});

test("a file of no kind, of several, of an app that is off, or too large is never sent", async () => {
  vi.stubGlobal("XMLHttpRequest", Upload);
  const { screen } = await open(PAGE, serving(offered()));
  await screen
    .getByLabelText("Upload files")
    .upload([
      new File(["x"], "notes.txt"),
      new File(["x"], "plan.dxf"),
      new File(["x"], "sums.xlsx"),
      new File(["x".repeat(1001)], "big.docx"),
    ]);
  for (const said of [
    "notes.txt isn't a kind of file this workspace takes.",
    "plan.dxf could be several kinds of file, so it can't be told which to make.",
    "GridCraft is off in this workspace, so sums.xlsx can't be uploaded.",
    "big.docx is 1 kB: the largest file an upload takes is 1 kB.",
  ]) {
    await expect.element(screen.getByText(said, { exact: true }).first()).toBeVisible();
  }
  expect(Upload.sent).toHaveLength(0);
  await screen.getByRole("button", { name: "Dismiss notes.txt" }).click();
  expect(screen.getByText("notes.txt", { exact: true }).elements()).toEqual([]);
});

test("one stopped, or whose answer never came, is sent again with the same id", async () => {
  vi.stubGlobal("XMLHttpRequest", Upload);
  const { screen } = await open(PAGE, serving(offered()));
  await screen.getByLabelText("Upload files").upload(new File(["one"], "brief.docx"));
  const first = await sent(1);
  await screen.getByRole("button", { name: "Stop uploading brief.docx" }).click();
  await expect
    .element(
      screen
        .getByText(/^brief\.docx wasn't uploaded: the connection ended, or it was stopped/)
        .first(),
    )
    .toBeVisible();
  await screen.getByRole("button", { name: "Try again to upload brief.docx" }).click();
  const again = await sent(2);
  expect(query(again).get("artifact_id")).toBe(query(first).get("artifact_id"));
  again.answer(200, { outcome: "unchanged", artifact_id: "a", version: null, proposal_id: null });
  await expect
    .element(screen.getByText("brief.docx was uploaded already: nothing new was made.").first())
    .toBeVisible();
});

test("a thread's files are made in it, beneath its composer", async () => {
  vi.stubGlobal("XMLHttpRequest", Upload);
  const uploads = serving(offered());
  const thread = async (request: Request, path: string) => {
    if (path === "/grantr/v1/checks") {
      const asked: unknown[] = await request.json();
      return Response.json(asked.map(() => true));
    }
    return path.startsWith("/grantr/v1/tenants/acme/") ? Response.json([]) : uploads(request, path);
  };
  const log = [
    {
      type: "event",
      seq: 1,
      id: "evt_1",
      ts: "2026-10-20T00:00:00Z",
      workspace_id: "notes",
      actor: { kind: "user", id: "alice" },
      event: { type: "thread_created", thread_id: "t_1", title: "Launch" },
    },
  ];
  const { screen } = await open("/t/acme/w/notes/threads/t_1", thread, undefined, {
    artifactrLog: log,
  });
  await screen.getByLabelText("Add files to this thread").upload(new File(["x"], "brief.docx"));
  expect(query(await sent(1)).get("thread_id")).toBe("t_1");
});

test("with every app off the chooser says why and takes nothing", async () => {
  const off = KINDS.map((kind) => ({ ...kind, enabled: false }));
  const { screen } = await open(PAGE, serving(offered({ kinds: off })));
  const input = screen.getByLabelText("Upload files");
  await expect.element(input).toBeDisabled();
  await expect
    .element(input)
    .toHaveAccessibleDescription(
      "No app for files is on in this workspace: an admin can switch one on in its integrations. Or drop them here.",
    );
});

test("whoever may not upload sees no chooser", async () => {
  const { screen } = await open(PAGE, serving(offered({ allowed: false })));
  await expect.element(screen.getByRole("heading", { name: "Artifacts" })).toBeVisible();
  expect(screen.getByLabelText("Upload files").elements()).toEqual([]);
});

test("a kind is told by its extension, whatever its case", () => {
  expect(kindsOf("PLAN.DWG", KINDS)).toEqual(["drawing"]);
  expect(kindsOf("plan.dxf", KINDS)).toEqual(["drawing", "other_drawing"]);
  expect(kindsOf("README", KINDS)).toEqual([]);
  expect([appOf("word_document"), appOf("mystery")]).toEqual(["WordCraft", "mystery"]);
});

test("each refusal is said in the portal's words, and those worth sending again say so", () => {
  const said = (status: number, change: object = {}) =>
    uploadRefused(
      { outcome: "refused", status, reasons: ["Why."], ...change },
      "a.docx",
      "WordCraft",
      2000,
    );
  expect(said(0, { reasons: ["<b>server text</b>"] })).toEqual({
    text: "a.docx wasn't uploaded: the connection ended, or it was stopped, before the server answered. It may have arrived: trying again never makes it twice.",
    again: true,
  });
  expect(said(408, { type: "too_slow" })).toEqual({
    text: "a.docx wasn't uploaded: the upload was too slow and was stopped. Try again.",
    again: true,
  });
  expect(said(401).text).toBe(
    "a.docx wasn't uploaded: you're signed out. Sign in, then try again.",
  );
  expect(said(403).text).toBe("a.docx wasn't uploaded: you can't upload files in this workspace.");
  expect(said(409, { type: "not_enabled" }).text).toBe(
    "a.docx wasn't uploaded: WordCraft is off in this workspace.",
  );
  expect(said(409, { type: "invalid_state" }).text).toMatch(/another file already has its id/);
  expect(said(413, { type: "over_quota", quota: "workspace_bytes" }).text).toBe(
    "a.docx wasn't uploaded: This workspace already holds as much as it may. Ask an admin for more room.",
  );
  expect(said(413, { type: "over_quota", quota: "tenant_files" }).text).toBe(
    "a.docx wasn't uploaded: Your organisation already holds as many files as it may. Ask an admin for more room.",
  );
  expect(said(413).text).toBe("a.docx is larger than the 2 kB an upload takes.");
  expect(said(422, { reasons: ["the app said <script>"] }).text).toBe(
    "WordCraft couldn't read a.docx: it may be damaged, or not the kind of file its name says.",
  );
  expect(said(429, { type: "busy" })).toEqual({
    text: "a.docx wasn't uploaded: the server is busy with other files just now. Try again in a few seconds.",
    again: true,
  });
  expect(said(429, { type: "rate_limited" }).text).toMatch(/many uploads in the last minute/);
  expect(said(503)).toEqual({
    text: "WordCraft couldn't finish reading a.docx. Try again in a moment.",
    again: true,
  });
  expect(said(500, { reasons: ["<b>server text</b>"] })).toEqual({
    text: "a.docx wasn't uploaded: the server refused it.",
    again: false,
  });
});

test("a file the app can't finish is offered again twice, and no more", async () => {
  vi.stubGlobal("XMLHttpRequest", Upload);
  const { screen } = await open(PAGE, serving(offered()));
  await screen.getByLabelText("Upload files").upload(new File(["x"], "brief.docx"));
  const crash = { detail: { type: "app_failed", failure: "crashed", message: "fixed" } };
  for (const count of [1, 2, 3]) {
    (await sent(count)).answer(503, crash);
    const retry = screen.getByRole("button", { name: "Try again to upload brief.docx" });
    if (count < 3) {
      await retry.click();
    } else {
      await expect
        .element(screen.getByRole("button", { name: "Dismiss brief.docx" }))
        .toBeVisible();
      expect(retry.elements()).toEqual([]);
    }
  }
});

test("leaving the page stops the file going", async () => {
  vi.stubGlobal("XMLHttpRequest", Upload);
  const { screen } = await open(PAGE, serving(offered()));
  await screen.getByLabelText("Upload files").upload(new File(["x"], "brief.docx"));
  const going = await sent(1);
  const aborted = vi.spyOn(going, "abort");
  screen.unmount();
  expect(aborted).toHaveBeenCalled();
});

test("a name's bidirectional controls are dropped from what is said of it", async () => {
  vi.stubGlobal("XMLHttpRequest", Upload);
  const { screen } = await open(PAGE, serving(offered()));
  await screen.getByLabelText("Upload files").upload(new File(["x"], "evil\u202Excod.txt"));
  await expect
    .element(screen.getByText("evilxcod.txt isn't a kind of file this workspace takes.").first())
    .toBeVisible();
});
