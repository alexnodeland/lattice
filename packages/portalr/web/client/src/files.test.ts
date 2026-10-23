import { QueryClient } from "@tanstack/react-query";
import type { Server } from "bun";
import { afterAll, afterEach, beforeAll, expect, test, vi } from "vitest";
import { createCommands } from "./commands";
import { checkIn, newArtifactId, pngDataUrl, uploadFile } from "./files";
import { createQueries, keys, Refused } from "./queries";
import { createApi } from "./rest";

const PNG = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
const AT = "/artifactr/v1/workspaces/ws_1";
const STATUS = {
  artifact_id: "doc_1",
  version: 2,
  name: "brief.docx",
  media_type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  size: 12,
  outline: "Brief",
  pages: 1,
  lease: null,
  talk: "save",
  enabled: true,
  limit: 26_214_400,
};

const UPLOADS = {
  allowed: true,
  limit: 26_214_400,
  kinds: [{ kind: "word_document", extensions: [".docx"], enabled: true }],
};

const seen: URL[] = [];
let server: Server<unknown>;
let queries: ReturnType<typeof createQueries>;
let commands: ReturnType<typeof createCommands>;
const CHECKOUT = {
  id: "co_1",
  artifact_id: "doc_1",
  base_version: 2,
  base_sha256: "a".repeat(64),
  actor: { kind: "user", id: "bob" },
  expires_at: "2026-10-17T17:30:00Z",
  checked_in: false,
};

beforeAll(() => {
  server = Bun.serve({
    port: 0,
    fetch(request) {
      const url = new URL(request.url);
      seen.push(url);
      switch (url.pathname) {
        case `${AT}/files/doc_1`:
          return Response.json(STATUS);
        case `${AT}/files/doc_1/versions/1/text`:
        case `${AT}/proposals/p_1/text`:
          return new Response("Brief\n\nStarts on Monday.", {
            headers: { "content-type": "text/plain" },
          });
        case `${AT}/files/doc_1/versions/2/text`:
          return Response.json({ detail: { type: "invalid_state" } }, { status: 409 });
        case `${AT}/files/doc_1/versions/1/pages/1`:
        case `${AT}/proposals/p_1/pages/1`:
          // Typed as anything: the page is a PNG whatever the response says.
          return new Response(PNG, { headers: { "content-type": "application/octet-stream" } });
        case `${AT}/files/doc_1/versions/1/content`:
          return new Response("the file's bytes");
        case `${AT}/uploads`:
          return Response.json(UPLOADS);
        case "/artifactr/v1/workspaces/ws_2/uploads":
          return Response.json({ detail: "not found" }, { status: 404 });
        case `${AT}/files/doc_1/checkouts`:
          return Response.json(CHECKOUT, { status: 201 });
        case `${AT}/checkouts/co_1/extension`:
          return Response.json({ ...CHECKOUT, expires_at: "2026-10-17T18:00:00Z" });
        case `${AT}/checkouts/co_2/extension`:
          return Response.json(
            { detail: { type: "invalid_state", message: "checkout co_2 was checked in" } },
            { status: 409 },
          );
        default:
          return Response.json({ detail: "not found" }, { status: 404 });
      }
    },
  });
  const origin = `http://127.0.0.1:${server.port}`;
  const api = createApi(
    { artifactr: `${origin}/artifactr/v1`, reflexr: "", grantr: origin },
    () => ({ token: "t0k3n" }),
  );
  queries = createQueries(api);
  commands = createCommands(api);
});

afterAll(() => {
  server.stop(true);
});

test("a PNG's bytes are a data: URL, however long", () => {
  expect(pngDataUrl(PNG.buffer)).toBe("data:image/png;base64,iVBORw0KGgo=");
  const large = new Uint8Array(100_000).fill(65);
  expect(atob(pngDataUrl(large.buffer).split(",")[1] ?? "")).toBe("A".repeat(100_000));
});

test("a file's status is read beside artifactr's routes, and again sooner while an agent edits", async () => {
  const options = queries.files.status("acme", "ws_1", "doc_1");
  expect(await new QueryClient().fetchQuery(options)).toEqual(STATUS);
  expect(seen.at(-1)?.pathname).toBe(`${AT}/files/doc_1`);
  const interval = options.refetchInterval as (query: unknown) => number;
  const leased = (checked_out_by: string | null) => ({
    state: { data: { ...STATUS, lease: { checked_out_by, expires_at: "" } } },
  });
  expect(interval({ state: { data: STATUS } })).toBe(30_000);
  expect(interval({ state: { status: "error" } })).toBe(false);
  expect(interval(leased("user:bob"))).toBe(30_000);
  expect(interval(leased(null))).toBe(2_000);
});

test("a version's words are its text, or null where it has none", async () => {
  const client = new QueryClient();
  expect(await client.fetchQuery(queries.files.text("acme", "ws_1", "doc_1", 1))).toBe(
    "Brief\n\nStarts on Monday.",
  );
  expect(await client.fetchQuery(queries.files.text("acme", "ws_1", "doc_1", 2))).toBeNull();
  await expect(
    client.fetchQuery(queries.files.text("acme", "ws_1", "doc_1", 3)),
  ).rejects.toBeInstanceOf(Refused);
});

test("pages are data: URLs, and a proposal's are read by the proposal", async () => {
  const client = new QueryClient();
  const url = "data:image/png;base64,iVBORw0KGgo=";
  expect(await client.fetchQuery(queries.files.page("acme", "ws_1", "doc_1", 1, 1))).toBe(url);
  expect(await client.fetchQuery(queries.files.proposedPage("acme", "ws_1", "p_1", 1))).toBe(url);
  expect(await client.fetchQuery(queries.files.proposedText("acme", "ws_1", "p_1"))).toBe(
    "Brief\n\nStarts on Monday.",
  );
});

test("a version's bytes are a Blob, kept no longer than it is read", async () => {
  const options = queries.files.content("acme", "ws_1", "doc_1", 1);
  const blob = await new QueryClient().fetchQuery(options);
  expect(await blob.text()).toBe("the file's bytes");
  expect(options.gcTime).toBe(0);
});

test("a change to a file makes its status stale, never its versions' words or pages", () => {
  const artifact = keys.artifactr.artifact("acme", "ws_1", "doc_1");
  const under = (key: readonly unknown[]) => artifact.every((part, index) => key[index] === part);
  expect(under(keys.files.status("acme", "ws_1", "doc_1"))).toBe(true);
  expect(under(keys.files.version("acme", "ws_1", "doc_1", 1))).toBe(false);
  expect(under(keys.files.proposal("acme", "ws_1", "p_1"))).toBe(false);
});

test("a check-out and its extension are commands on the file and the check-out", async () => {
  const checkedOut = await commands.files.checkOut("acme", "ws_1", "doc_1");
  expect(checkedOut).toEqual({ outcome: "done", result: CHECKOUT });
  const extended = await commands.files.extend("acme", "ws_1", "co_1");
  expect(extended.outcome === "done" && extended.result.expires_at).toBe("2026-10-17T18:00:00Z");
  expect(await commands.files.extend("acme", "ws_1", "co_2")).toEqual({
    outcome: "refused",
    status: 409,
    reasons: ["That can't be done as things stand."],
  });
});

/** An `XMLHttpRequest` that keeps what it was sent, and answers as a test tells it. */
class Upload {
  static last: Upload;
  method = "";
  url = "";
  headers: Record<string, string> = {};
  body: unknown = null;
  status = 0;
  responseText = "";
  upload: { onprogress: ((progress: { loaded: number; total: number }) => void) | null } = {
    onprogress: null,
  };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onabort: (() => void) | null = null;

  constructor() {
    Upload.last = this;
  }
  open(method: string, url: string) {
    this.method = method;
    this.url = url;
  }
  setRequestHeader(name: string, value: string) {
    this.headers[name] = value;
  }
  send(body: unknown) {
    this.body = body;
  }
  abort() {
    this.onabort?.();
  }
  answer(status: number, body: unknown) {
    this.status = status;
    this.responseText = typeof body === "string" ? body : JSON.stringify(body);
    this.onload?.();
  }
}

afterEach(() => {
  vi.unstubAllGlobals();
});

const sending = (signal?: AbortSignal) => {
  const progress: [number, number][] = [];
  const answer = checkIn({
    surface: "/artifactr/v1/",
    session: { token: "t0k3n" },
    tenant: "acme",
    workspace: "ws 1",
    checkout: "co_1",
    file: new Blob(["edited"]),
    onProgress: (sent, total) => progress.push([sent, total]),
    ...(signal && { signal }),
  });
  return { answer, progress, xhr: Upload.last };
};

test("a check-in puts the file to its check-out, as the reader, and says how far it has gone", async () => {
  vi.stubGlobal("XMLHttpRequest", Upload);
  const { answer, progress, xhr } = sending();
  expect([xhr.method, xhr.url]).toEqual([
    "PUT",
    "/artifactr/v1/workspaces/ws%201/checkouts/co_1/file",
  ]);
  expect(xhr.headers).toEqual({
    Authorization: "Bearer t0k3n",
    "X-Tenant": "acme",
    "Content-Type": "application/octet-stream",
  });
  expect(xhr.body).toBeInstanceOf(Blob);
  xhr.upload.onprogress?.({ loaded: 3, total: 6 });
  xhr.answer(200, { outcome: "applied", version: 3, proposal_id: null });
  expect(await answer).toEqual({
    outcome: "done",
    result: { outcome: "applied", version: 3, proposal_id: null },
  });
  expect(progress).toEqual([[3, 6]]);
});

test("a check-in refused says why, and one never answered or stopped is status 0", async () => {
  vi.stubGlobal("XMLHttpRequest", Upload);
  const refused = sending();
  refused.xhr.answer(413, { detail: "the file is larger than 4096 bytes" });
  expect(await refused.answer).toEqual({
    outcome: "refused",
    status: 413,
    reasons: ["That's too large."],
  });
  const garbled = sending();
  garbled.xhr.answer(502, "Bad Gateway");
  expect(await garbled.answer).toEqual({
    outcome: "refused",
    status: 502,
    reasons: ["The server had a problem. Try again in a moment."],
  });
  const dropped = sending();
  dropped.xhr.onerror?.();
  expect(await dropped.answer).toEqual({
    outcome: "refused",
    status: 0,
    reasons: ["The connection ended before the server answered."],
  });
  const stop = new AbortController();
  const stopped = sending(stop.signal);
  stop.abort();
  expect(await stopped.answer).toEqual({
    outcome: "refused",
    status: 0,
    reasons: ["The check-in was stopped: what was sent may still have been checked in."],
  });
  const already = new AbortController();
  already.abort();
  expect(await sending(already.signal).answer).toMatchObject({ outcome: "refused", status: 0 });
});

test("a check-in refused says its rejection's type, and one refused unsigned ends the session", async () => {
  vi.stubGlobal("XMLHttpRequest", Upload);
  const busy = sending();
  busy.xhr.answer(409, { detail: { type: "invalid_state", message: "checked in already" } });
  expect(await busy.answer).toEqual({
    outcome: "refused",
    status: 409,
    reasons: ["That can't be done as things stand."],
    type: "invalid_state",
  });
  let unsigned = 0;
  const answer = checkIn({
    surface: "/artifactr/v1",
    session: { token: null },
    tenant: "acme",
    workspace: "ws_1",
    checkout: "co_1",
    file: new Blob(["edited"]),
    unsigned: () => {
      unsigned += 1;
    },
  });
  Upload.last.answer(401, { detail: "sign in" });
  expect(await answer).toMatchObject({ outcome: "refused", status: 401 });
  expect(unsigned).toBe(1);
});

test("what may be uploaded is read beside artifactr's routes, every half minute, under the integrations", async () => {
  const client = new QueryClient();
  const options = queries.files.uploads("acme", "ws_1");
  expect(options.queryKey).toEqual([...keys.grantr.integrations("acme"), "uploads", "ws_1"]);
  expect(await client.fetchQuery(options)).toEqual(UPLOADS);
  const interval = options.refetchInterval as (query: unknown) => number | false;
  expect(interval({ state: { status: "success" } })).toBe(30_000);
  expect(interval({ state: { status: "error" } })).toBe(false);
  await expect(client.fetchQuery(queries.files.uploads("acme", "ws_2"))).rejects.toBeInstanceOf(
    Refused,
  );
});

const uploading = (thread?: string) =>
  uploadFile({
    surface: "/artifactr/v1",
    session: { token: "t0k3n" },
    tenant: "acme",
    workspace: "ws 1",
    kind: "word_document",
    name: "brief & co.docx",
    artifact: "art_1",
    ...(thread !== undefined && { thread }),
    file: new File(["new"], "brief.docx"),
  });

test("an upload posts the file to the workspace, of its kind and named, with the id it chose", async () => {
  vi.stubGlobal("XMLHttpRequest", Upload);
  const answer = uploading("t 1");
  const xhr = Upload.last;
  expect([xhr.method, xhr.url]).toEqual([
    "POST",
    "/artifactr/v1/workspaces/ws%201/files?kind=word_document&name=brief+%26+co.docx&artifact_id=art_1&thread_id=t+1",
  ]);
  expect(xhr.body).toBeInstanceOf(File);
  xhr.answer(201, { outcome: "applied", artifact_id: "art_1", version: 1, proposal_id: null });
  expect(await answer).toMatchObject({ outcome: "done", result: { outcome: "applied" } });
  uploading();
  expect(Upload.last.url).not.toContain("thread_id");
});

test("an upload refused past a quota says which, and one stopped says it may have landed", async () => {
  vi.stubGlobal("XMLHttpRequest", Upload);
  const full = uploading();
  Upload.last.answer(413, {
    detail: { type: "over_quota", quota: "workspace_files", limit: 3 },
  });
  expect(await full).toEqual({
    outcome: "refused",
    status: 413,
    reasons: ["There's no room left here."],
    type: "over_quota",
    quota: "workspace_files",
  });
  const odd = uploading();
  Upload.last.answer(429, { detail: { type: 7, quota: null } });
  expect(await odd).toEqual({
    outcome: "refused",
    status: 429,
    reasons: ["Too much was asked at once. Try again in a moment."],
  });
  const stop = new AbortController();
  stop.abort();
  const stopped = await uploadFile({
    surface: "/artifactr/v1",
    session: { token: "t0k3n" },
    tenant: "acme",
    workspace: "ws_1",
    kind: "word_document",
    name: "brief.docx",
    artifact: "art_1",
    file: new Blob(["new"]),
    signal: stop.signal,
  });
  expect(stopped).toMatchObject({
    reasons: ["The upload was stopped: what was sent may still have been uploaded."],
  });
});

test("an upload's id is new each time, of artifactr's form", () => {
  const id = newArtifactId();
  expect(id).toMatch(/^art_[0-9a-f]{16}$/);
  expect(newArtifactId()).not.toBe(id);
});
