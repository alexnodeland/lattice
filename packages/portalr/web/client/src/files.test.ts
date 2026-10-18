import { QueryClient } from "@tanstack/react-query";
import type { Server } from "bun";
import { afterAll, beforeAll, expect, test } from "vitest";
import { pngDataUrl } from "./files";
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

const seen: URL[] = [];
let server: Server<unknown>;
let queries: ReturnType<typeof createQueries>;

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
        default:
          return Response.json({ detail: "not found" }, { status: 404 });
      }
    },
  });
  const origin = `http://127.0.0.1:${server.port}`;
  queries = createQueries(
    createApi({ artifactr: `${origin}/artifactr/v1`, reflexr: "", grantr: origin }, () => ({
      token: "t0k3n",
    })),
  );
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
